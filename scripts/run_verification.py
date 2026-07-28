"""Generate a machine-readable software verification record.

Timing values describe the development host only and are never UNO Q results.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
from cryptography.exceptions import InvalidTag

SCRIPT_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SOFTWARE_ROOT / "python"))

from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import (
    PacketReplayError,
    ProtectedPacket,
    RoiProtector,
    RoiReceiver,
)
from unoq_lorenz.pipeline import protect_frame, recover_frame


def core_source_sha256() -> str:
    digest = hashlib.sha256()
    source_root = SOFTWARE_ROOT / "python" / "unoq_lorenz"
    for path in sorted(source_root.glob("*.py")):
        relative = path.relative_to(SOFTWARE_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def main() -> None:
    rng = np.random.default_rng(20260720)
    initialization_started = time.perf_counter_ns()
    protector = RoiProtector(bytes(range(32)))
    protector_initialization_ms = (
        time.perf_counter_ns() - initialization_started
    ) / 1_000_000.0
    receiver = RoiReceiver(protector)
    nonces = NonceSequence(b"HOST2026")
    run_id = "host-verification-v2"
    rows = []
    exact_recoveries = 0
    tamper_rejections = 0
    replay_rejections = 0
    serialization_round_trips = 0
    observed_nonces: set[bytes] = set()
    observed_packet_ids: set[int] = set()

    for case_id in range(50):
        height = int(rng.integers(28, 65))
        width = int(rng.integers(28, 65))
        frame = rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
        box = (12, 14, 12 + width, 14 + height)

        started = time.perf_counter_ns()
        protected = protect_frame(
            frame,
            [box],
            run_id=run_id,
            frame_id=case_id,
            protector=protector,
            nonces=nonces,
            use_lorenz=True,
        )
        encrypted_ns = time.perf_counter_ns() - started

        started = time.perf_counter_ns()
        recovered = recover_frame(
            protected.preview,
            protected.packets,
            protector=protector,
        )
        decrypted_ns = time.perf_counter_ns() - started
        exact = bool(np.array_equal(recovered, frame))
        exact_recoveries += int(exact)

        packet = protected.packets[0]
        serialized_packet = ProtectedPacket.from_json(packet.to_json())
        serialization_round_trip = serialized_packet == packet
        serialization_round_trips += int(serialization_round_trip)
        observed_nonces.add(packet.nonce)
        observed_packet_ids.add(packet.metadata.packet_id)
        changed = bytearray(packet.ciphertext_and_tag)
        changed[case_id % len(changed)] ^= 1
        try:
            protector.decrypt(
                ProtectedPacket(packet.metadata, packet.nonce, bytes(changed))
            )
            tamper_rejected = False
        except InvalidTag:
            tamper_rejected = True
        tamper_rejections += int(tamper_rejected)

        receiver.receive(serialized_packet)
        try:
            receiver.receive(serialized_packet)
            replay_rejected = False
        except PacketReplayError:
            replay_rejected = True
        replay_rejections += int(replay_rejected)

        rows.append(
            {
                "case_id": case_id,
                "roi_width": width,
                "roi_height": height,
                "roi_bytes": width * height * 3,
                "packet_id": packet.metadata.packet_id,
                "encrypt_ms_host": encrypted_ns / 1_000_000.0,
                "decrypt_ms_host": decrypted_ns / 1_000_000.0,
                "exact_recovery": int(exact),
                "tamper_rejected": int(tamper_rejected),
                "replay_rejected": int(replay_rejected),
                "serialization_round_trip": int(serialization_round_trip),
            }
        )

    data_dir = SOFTWARE_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / "software_verification_cases.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    expected = len(rows)
    passed = all(
        value == expected
        for value in (
            exact_recoveries,
            tamper_rejections,
            replay_rejections,
            serialization_round_trips,
            len(observed_nonces),
            len(observed_packet_ids),
        )
    )
    summary = {
        "status": (
            "passed_software_verification_on_development_host"
            if passed
            else "failed_software_verification_on_development_host"
        ),
        "all_required_checks_passed": passed,
        "not_uno_q_measurements": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_source_sha256": core_source_sha256(),
        "cases": len(rows),
        "exact_recoveries": exact_recoveries,
        "tamper_rejections": tamper_rejections,
        "replay_rejections": replay_rejections,
        "serialization_round_trips": serialization_round_trips,
        "unique_nonces": len(observed_nonces),
        "unique_packet_ids": len(observed_packet_ids),
        "protector_initialization_ms_host": protector_initialization_ms,
        "median_encrypt_ms_host": statistics.median(
            row["encrypt_ms_host"] for row in rows
        ),
        "median_decrypt_ms_host": statistics.median(
            row["decrypt_ms_host"] for row in rows
        ),
        "python": platform.python_version(),
        "platform_family": platform.system(),
        "random_seed": 20260720,
        "run_id": run_id,
        "protocol_version": rows and protected.packets[0].metadata.protocol_version,
        "transform_version": protector.transform_version,
        "transform_profile_sha256": protector.transform_profile_sha256,
        "conditions": (
            "Lorenz v2 transform followed by ChaCha20-Poly1305; "
            "stateful replay rejection"
        ),
    }
    (data_dir / "software_verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    if not passed:
        raise SystemExit("software verification failed one or more invariants")


if __name__ == "__main__":
    main()

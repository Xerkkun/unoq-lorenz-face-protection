"""Atomic persistence for authenticated, recoverable ROI packet bundles."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .packet import ProtectedPacket, RoiProtector
from .protocol import validate_run_id


BUNDLE_SCHEMA = "unoq-protected-frame-bundle-v1"
RUN_CONTRACT_SCHEMA = "unoq-run-contract-v1"


@dataclass(frozen=True)
class StoredFrameBundle:
    path: Path
    serialized_bytes: int
    sha256: str
    packet_count: int


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def _atomic_write_new(destination: Path, payload: bytes) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing evidence: {destination}")
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # A hard link publishes the already-complete inode and, unlike
        # os.replace(), fails if another callback created the same evidence
        # name between the initial check and this operation.
        os.link(temporary, destination)
        temporary.unlink()
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


class PacketStore:
    """One exclusive packet directory for one fresh-key experiment run."""

    def __init__(
        self,
        root: str | Path,
        *,
        run_id: str,
        condition: str,
        scene: str,
        bbox_margin_fraction: float,
        key_fingerprint_sha256: str,
        key_origin: str,
        nonce_prefix: bytes,
        protector: RoiProtector,
    ) -> None:
        self.run_id = validate_run_id(run_id)
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if len(key_fingerprint_sha256) != 64:
            raise ValueError("key fingerprint must be SHA-256 hex")
        if len(nonce_prefix) != 8:
            raise ValueError("nonce prefix must contain eight bytes")

        self._reject_reused_key(key_fingerprint_sha256)
        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir(mode=0o700, exist_ok=False)
        contract = {
            "schema": RUN_CONTRACT_SCHEMA,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "condition": condition,
            "scene": scene,
            "bbox_margin_fraction": bbox_margin_fraction,
            "run_key_policy": protector.run_key_policy,
            "key_fingerprint_sha256": key_fingerprint_sha256,
            "key_origin": key_origin,
            "nonce_prefix_hex": nonce_prefix.hex(),
            "protocol_version": protector.metadata(
                run_id=self.run_id,
                packet_id=0,
                frame_id=0,
                roi_id=0,
                x0=0,
                y0=0,
                x1=1,
                y1=1,
                height=1,
                width=1,
                channels=1,
                use_lorenz=True,
            ).protocol_version,
            "aead_algorithm": protector.aead_algorithm,
            "kdf_profile": protector.kdf_profile,
            "transform_version": protector.transform_version,
            "transform_profile_sha256": protector.transform_profile_sha256,
            "secret_material_in_contract": False,
        }
        _atomic_write_new(
            self.run_dir / "run_contract.json",
            _canonical_json_bytes(contract),
        )

    def _reject_reused_key(self, fingerprint: str) -> None:
        for contract_path in sorted(self.root.glob("*/run_contract.json")):
            try:
                contract = json.loads(contract_path.read_text(encoding="ascii"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"cannot validate existing run contract: {contract_path}"
                ) from error
            if contract.get("key_fingerprint_sha256") == fingerprint:
                raise ValueError(
                    "run key was already recorded under another run; generate a "
                    "fresh 32-byte key before starting"
                )

    def store_frame(
        self,
        packets: Iterable[ProtectedPacket],
    ) -> StoredFrameBundle:
        packet_tuple = tuple(packets)
        if not packet_tuple:
            raise ValueError("an authenticated frame bundle must contain packets")
        frame_ids = {packet.metadata.frame_id for packet in packet_tuple}
        run_ids = {packet.metadata.run_id for packet in packet_tuple}
        packet_ids = [packet.metadata.packet_id for packet in packet_tuple]
        if run_ids != {self.run_id}:
            raise ValueError("packet run_id does not match this store")
        if len(frame_ids) != 1:
            raise ValueError("one frame bundle cannot mix frame identifiers")
        if len(set(packet_ids)) != len(packet_ids):
            raise ValueError("one frame bundle contains duplicate packet identifiers")
        frame_id = next(iter(frame_ids))
        payload = {
            "schema": BUNDLE_SCHEMA,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "frame_id": frame_id,
            "packet_count": len(packet_tuple),
            "packets": [packet.to_dict() for packet in packet_tuple],
        }
        serialized = _canonical_json_bytes(payload)
        destination = self.run_dir / f"frame_{frame_id:010d}.json"
        _atomic_write_new(destination, serialized)
        return StoredFrameBundle(
            path=destination,
            serialized_bytes=len(serialized),
            sha256=hashlib.sha256(serialized).hexdigest(),
            packet_count=len(packet_tuple),
        )


def load_frame_bundle(path: str | Path) -> tuple[ProtectedPacket, ...]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid packet bundle: {source}") from error
    if payload.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("unsupported packet-bundle schema")
    packets_payload = payload.get("packets")
    if not isinstance(packets_payload, list) or not packets_payload:
        raise ValueError("packet bundle contains no packets")
    packets = tuple(ProtectedPacket.from_dict(item) for item in packets_payload)
    if payload.get("packet_count") != len(packets):
        raise ValueError("packet bundle count does not match its contents")
    if {packet.metadata.run_id for packet in packets} != {payload.get("run_id")}:
        raise ValueError("packet bundle run_id does not match packet metadata")
    if {packet.metadata.frame_id for packet in packets} != {payload.get("frame_id")}:
        raise ValueError("packet bundle frame_id does not match packet metadata")
    return packets

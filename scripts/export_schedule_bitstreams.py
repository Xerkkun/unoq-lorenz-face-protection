"""Export deterministic teaching bitstreams from the registered M4 schedule.

The output contains PCG64 mask bytes derived from the versioned Lorenz schedule.
It is intended for reproducible statistical characterization, never for keys,
nonces, production encryption, or claims of cryptographic security.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SOFTWARE_ROOT / "python"))

from unoq_lorenz.kdf import derive_experiment_subkeys
from unoq_lorenz.transform import LorenzTransform


DOMAIN = b"unoq-lorenz-statistical-teaching-streams-v1"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_mask_streams(
    output_dir: Path,
    *,
    seed_label: str,
    stream_count: int,
    bytes_per_stream: int,
) -> dict[str, object]:
    """Write independent nonce-indexed mask streams and a deterministic manifest."""

    if not seed_label or len(seed_label.encode("utf-8")) > 256:
        raise ValueError("seed_label must contain 1 to 256 UTF-8 bytes")
    if not 1 <= stream_count <= 10_000:
        raise ValueError("stream_count must be within [1, 10000]")
    if not 1 <= bytes_per_stream <= 1_000_000_000:
        raise ValueError("bytes_per_stream must be within [1, 1000000000]")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("output directory must not contain existing files")
    output_dir.mkdir(parents=True, exist_ok=True)

    label_bytes = seed_label.encode("utf-8")
    demo_master_key = hashlib.sha256(DOMAIN + b"/master/" + label_bytes).digest()
    _, schedule_key = derive_experiment_subkeys(demo_master_key)
    transform = LorenzTransform(schedule_key)
    nonce_prefix = hashlib.sha256(
        DOMAIN + b"/nonce-prefix/" + label_bytes
    ).digest()[:8]

    files: list[dict[str, object]] = []
    for stream_id in range(stream_count):
        nonce = nonce_prefix + stream_id.to_bytes(4, "big")
        _, mask = transform.schedule(nonce, bytes_per_stream)
        destination = output_dir / f"mask_stream_{stream_id:04d}.bin"
        destination.write_bytes(mask.tobytes())
        files.append(
            {
                "bytes": bytes_per_stream,
                "nonce_hex": nonce.hex(),
                "path": destination.name,
                "sha256": _sha256_file(destination),
                "stream_id": stream_id,
            }
        )

    manifest: dict[str, object] = {
        "artifact_type": "deterministic_teaching_bitstreams",
        "bytes_per_stream": bytes_per_stream,
        "generator_output": "numpy_pcg64_uint8_mask_after_registered_permutation",
        "master_material": (
            "deterministic public teaching material derived from seed_label; "
            "not a production secret"
        ),
        "nonce_construction": "deterministic_64_bit_prefix_plus_be32_stream_id",
        "profile_sha256": transform.config.profile_sha256,
        "purpose": (
            "statistical characterization and classroom reproduction only; "
            "passing tests does not prove cryptographic security"
        ),
        "seed_label": seed_label,
        "stream_count": stream_count,
        "streams": files,
        "transform_version": transform.config.version,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export raw mask bytes from the registered Lorenz/PCG64 schedule "
            "for teaching and statistical characterization."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--seed-label",
        default="engineering-classroom-example-01",
        help="public deterministic label; never pass a production key",
    )
    parser.add_argument("--stream-count", type=int, default=10)
    parser.add_argument("--bytes-per-stream", type=int, default=1_000_000)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = export_mask_streams(
        args.output_dir,
        seed_label=args.seed_label,
        stream_count=args.stream_count,
        bytes_per_stream=args.bytes_per_stream,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Fresh per-run key loading and private generation helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .protocol import validate_run_id


@dataclass(frozen=True)
class RunKeyMaterial:
    key: bytes
    fingerprint_sha256: str
    origin: str
    private_path: Path | None = None


def _decode_key(payload: bytes | str, *, source: str) -> bytes:
    if isinstance(payload, str):
        raw = payload.strip().encode("ascii")
    else:
        raw = bytes(payload)
        if len(raw) == 32:
            return raw
        raw = raw.strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{source} must contain 32 raw bytes or valid base64") from error
    if len(key) != 32:
        raise ValueError(f"{source} must resolve to exactly 32 bytes")
    return key


def _check_private_permissions(path: Path) -> None:
    """Reject group/world-readable secret files on POSIX systems."""

    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(
            f"run-key file must not grant group/world permissions: {path}"
        )


def _generate_private_key(run_id: str, secret_dir: Path) -> tuple[bytes, Path]:
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(secret_dir, 0o700)
    destination = secret_dir / f"{run_id}.key"
    key = os.urandom(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    _check_private_permissions(destination)
    return key, destination


def load_or_create_run_key(
    run_id: str,
    *,
    encoded_key: str | None = None,
    key_file: str | Path | None = None,
    secret_dir: str | Path = "/app/data/private",
) -> RunKeyMaterial:
    """Load one explicitly supplied run key or generate a private fresh key.

    Supplying both sources is rejected.  With no supplied source, a raw 32-byte
    key is created using ``os.urandom`` in an exclusive, mode-0600 file.  An
    existing file for the same run id is a hard failure: restarting requires a
    new run id and a new key rather than resetting the nonce counter.
    """

    validate_run_id(run_id)
    if encoded_key and key_file:
        raise ValueError("provide either UNOQ_MASTER_KEY_B64 or UNOQ_MASTER_KEY_FILE")

    private_path: Path | None = None
    if encoded_key:
        key = _decode_key(encoded_key, source="UNOQ_MASTER_KEY_B64")
        origin = "environment"
    elif key_file:
        private_path = Path(key_file)
        if not private_path.is_file():
            raise FileNotFoundError(f"run-key file does not exist: {private_path}")
        _check_private_permissions(private_path)
        key = _decode_key(private_path.read_bytes(), source="UNOQ_MASTER_KEY_FILE")
        origin = "private_file"
    else:
        key, private_path = _generate_private_key(run_id, Path(secret_dir))
        origin = "generated_private_file"

    return RunKeyMaterial(
        key=key,
        fingerprint_sha256=hashlib.sha256(key).hexdigest(),
        origin=origin,
        private_path=private_path,
    )

"""Identifiers and validation rules for the authenticated ROI protocol."""

from __future__ import annotations

import re


PROTOCOL_VERSION = "unoq-roi-packet-v2"
AEAD_ALGORITHM = "chacha20-poly1305-rfc8439"
KDF_PROFILE = "hkdf-sha256-unoq-roi-v2"
RUN_KEY_POLICY = "fresh-random-256-bit-key-per-run"

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_run_id(run_id: str) -> str:
    """Return a canonical, portable run identifier or raise ``ValueError``."""

    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id must contain 1--64 filename-safe ASCII characters "
            "(letters, digits, '.', '_' or '-', starting with alphanumeric)"
        )
    return run_id

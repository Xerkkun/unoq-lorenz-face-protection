"""Small RFC 5869 compatible HKDF-SHA-256 helper."""

from __future__ import annotations

import hashlib
import hmac


def hkdf_sha256(
    input_key_material: bytes,
    *,
    salt: bytes,
    info: bytes,
    length: int,
) -> bytes:
    """Derive ``length`` bytes using HKDF-Extract and HKDF-Expand."""

    if not input_key_material:
        raise ValueError("input key material must not be empty")
    if length <= 0 or length > 255 * hashlib.sha256().digest_size:
        raise ValueError("invalid HKDF output length")

    effective_salt = salt or bytes(hashlib.sha256().digest_size)
    pseudorandom_key = hmac.new(
        effective_salt, input_key_material, hashlib.sha256
    ).digest()

    output = bytearray()
    previous = b""
    counter = 1
    while len(output) < length:
        previous = hmac.new(
            pseudorandom_key,
            previous + info + bytes([counter]),
            hashlib.sha256,
        ).digest()
        output.extend(previous)
        counter += 1
    return bytes(output[:length])


def derive_experiment_subkeys(master_key: bytes) -> tuple[bytes, bytes]:
    """Return independent AEAD and Lorenz-schedule keys for protocol v2.

    ``master_key`` is a run key: callers must generate a fresh, uniformly
    random 32-byte value for each experiment run.
    """

    if len(master_key) != 32:
        raise ValueError("master key must contain exactly 32 bytes")
    salt = b"unoq-lorenz-roi-v2/subkeys"
    aead_key = hkdf_sha256(
        master_key,
        salt=salt,
        info=b"chacha20-poly1305",
        length=32,
    )
    lorenz_key = hkdf_sha256(
        master_key,
        salt=salt,
        info=b"lorenz-permutation-diffusion",
        length=32,
    )
    return aead_key, lorenz_key

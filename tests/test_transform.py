import hashlib

import numpy as np

from unoq_lorenz.transform import LorenzTransform, LorenzTransformConfig


KEY = bytes(range(32))
NONCE = bytes.fromhex("00112233445566778899aabb")


def test_lorenz_transform_round_trip():
    transform = LorenzTransform(KEY)
    plaintext = np.arange(4_096, dtype=np.uint16).astype(np.uint8).tobytes()
    transformed = transform.forward(plaintext, NONCE)
    assert transformed != plaintext
    assert transform.inverse(transformed, NONCE) == plaintext


def test_schedule_changes_with_nonce():
    transform = LorenzTransform(KEY)
    plaintext = bytes(range(256)) * 4
    first = transform.forward(plaintext, NONCE)
    second = transform.forward(plaintext, bytes.fromhex("10112233445566778899aabb"))
    assert first != second


def test_transform_profile_is_canonical_and_hash_bound():
    config = LorenzTransformConfig()
    profile = config.canonical_profile_json()
    assert profile == LorenzTransformConfig().canonical_profile_json()
    assert profile.startswith('{"burn_in":2048,')
    assert hashlib.sha256(profile.encode("ascii")).hexdigest() == config.profile_sha256
    assert LorenzTransformConfig(dt=0.006).profile_sha256 != config.profile_sha256

import json

import numpy as np
import pytest

from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.packet_store import PacketStore, load_frame_bundle
from unoq_lorenz.pipeline import protect_frame


def _make_store(tmp_path, *, run_id="run01", key=bytes(range(32))):
    protector = RoiProtector(key)
    nonces = NonceSequence(b"STORE001")
    store = PacketStore(
        tmp_path / "packets",
        run_id=run_id,
        condition="M4_lorenz_aead",
        scene="synthetic",
        bbox_margin_fraction=0.1,
        key_fingerprint_sha256=__import__("hashlib").sha256(key).hexdigest(),
        key_origin="test",
        nonce_prefix=nonces.prefix,
        protector=protector,
    )
    return store, protector, nonces


def test_atomic_bundle_round_trip_is_recoverable(tmp_path):
    store, protector, nonces = _make_store(tmp_path)
    frame = np.arange(40 * 48 * 3, dtype=np.uint16).astype(np.uint8).reshape(40, 48, 3)
    result = protect_frame(
        frame,
        [(4, 5, 30, 32)],
        run_id="run01",
        frame_id=7,
        protector=protector,
        nonces=nonces,
        use_lorenz=True,
    )
    stored = store.store_frame(result.packets)
    packets = load_frame_bundle(stored.path)
    assert stored.packet_count == 1
    assert stored.serialized_bytes == stored.path.stat().st_size
    assert np.array_equal(protector.decrypt(packets[0]), frame[5:32, 4:30])


def test_store_rejects_run_directory_and_key_reuse(tmp_path):
    _make_store(tmp_path)
    with pytest.raises(ValueError, match="already recorded"):
        _make_store(tmp_path, run_id="run02")


def test_loader_rejects_count_mismatch(tmp_path):
    store, protector, nonces = _make_store(tmp_path)
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    result = protect_frame(
        frame,
        [(1, 1, 9, 9)],
        run_id="run01",
        frame_id=2,
        protector=protector,
        nonces=nonces,
        use_lorenz=False,
    )
    stored = store.store_frame(result.packets)
    payload = json.loads(stored.path.read_text(encoding="ascii"))
    payload["packet_count"] = 2
    stored.path.write_text(json.dumps(payload), encoding="ascii")
    with pytest.raises(ValueError, match="count"):
        load_frame_bundle(stored.path)

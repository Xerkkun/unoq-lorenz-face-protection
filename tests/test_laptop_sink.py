import hashlib
import importlib.util
import threading
from http.client import HTTPConnection
from pathlib import Path

import numpy as np
import pytest

from unoq_lorenz.laptop_sink import (
    LaptopBundleDispatcher,
    ReceivedBundleStore,
    build_request_auth,
    verify_request_auth,
)
from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.packet_store import PacketStore
from unoq_lorenz.pipeline import protect_frame


def _stored_bundle(tmp_path):
    key = bytes(range(32))
    protector = RoiProtector(key)
    nonces = NonceSequence(b"LAPTOP01")
    store = PacketStore(
        tmp_path / "board",
        run_id="laptop_test",
        condition="M4_lorenz_aead",
        scene="synthetic",
        bbox_margin_fraction=0.1,
        key_fingerprint_sha256=hashlib.sha256(key).hexdigest(),
        key_origin="test",
        nonce_prefix=nonces.prefix,
        protector=protector,
    )
    frame = np.arange(24 * 32 * 3, dtype=np.uint16).astype(np.uint8)
    frame = frame.reshape(24, 32, 3)
    protected = protect_frame(
        frame,
        [(3, 4, 20, 18)],
        run_id="laptop_test",
        frame_id=9,
        protector=protector,
        nonces=nonces,
        use_lorenz=True,
    )
    return store.store_frame(protected.packets)


def test_request_auth_detects_body_tampering():
    token = b"T" * 32
    body = b'{"test":1}\n'
    headers = build_request_auth(token, body, timestamp=1_000)
    digest = verify_request_auth(token, body, headers, now=1_001)
    assert digest == hashlib.sha256(body).hexdigest()
    with pytest.raises(ValueError, match="digest"):
        verify_request_auth(token, body + b" ", headers, now=1_001)


def test_received_store_is_atomic_and_idempotent(tmp_path):
    bundle = _stored_bundle(tmp_path)
    payload = bundle.path.read_bytes()
    receiver = ReceivedBundleStore(tmp_path / "laptop")
    first = receiver.store(payload, bundle.sha256)
    second = receiver.store(payload, bundle.sha256)
    assert first.path == second.path
    assert not first.duplicate
    assert second.duplicate
    assert first.path.read_bytes() == payload


def test_received_store_rejects_same_frame_with_different_bytes(tmp_path):
    bundle = _stored_bundle(tmp_path)
    payload = bundle.path.read_bytes()
    receiver = ReceivedBundleStore(tmp_path / "laptop")
    receiver.store(payload, bundle.sha256)
    changed = payload.replace(b'"created_at_utc":"', b'"created_at_utc":"x', 1)
    with pytest.raises(FileExistsError, match="different bytes"):
        receiver.store(changed, hashlib.sha256(changed).hexdigest())


def test_dispatcher_delivers_the_board_persisted_bytes(tmp_path):
    bundle = _stored_bundle(tmp_path)
    calls = []

    def sender(url, payload, headers, timeout_seconds):
        calls.append((url, payload, headers, timeout_seconds))
        return 201

    dispatcher = LaptopBundleDispatcher(
        "http://192.168.10.20:8765/v1/bundles",
        b"S" * 32,
        sender=sender,
    )
    assert dispatcher.submit(bundle)
    assert dispatcher.wait_until_idle(2.0)
    snapshot = dispatcher.snapshot()
    assert snapshot.delivered == 1
    assert snapshot.failed == 0
    assert calls[0][1] == bundle.path.read_bytes()
    assert calls[0][2]["X-UNOQ-Run-ID"] == "laptop_test"


def test_http_receiver_accepts_one_authenticated_bundle(tmp_path):
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "laptop_packet_receiver.py"
    )
    spec = importlib.util.spec_from_file_location("laptop_packet_receiver", script_path)
    assert spec is not None and spec.loader is not None
    receiver_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receiver_module)

    token = b"H" * 32
    server = receiver_module.BundleReceiverServer(
        ("127.0.0.1", 0),
        store=ReceivedBundleStore(tmp_path / "received"),
        token=token,
        max_bytes=1_000_000,
        max_clock_skew_seconds=300,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        bundle = _stored_bundle(tmp_path)
        payload = bundle.path.read_bytes()
        headers = {
            "Content-Type": "application/json",
            **build_request_auth(token, payload),
        }
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("POST", "/v1/bundles", body=payload, headers=headers)
        response = connection.getresponse()
        response.read()
        connection.close()
        assert response.status == 201
        destination = (
            tmp_path
            / "received"
            / "laptop_test"
            / "frame_0000000009.json"
        )
        assert destination.read_bytes() == payload
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

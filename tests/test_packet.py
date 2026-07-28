from dataclasses import replace

import numpy as np
import pytest
from cryptography.exceptions import InvalidTag

from unoq_lorenz.packet import (
    PacketProfileMismatch,
    PacketReplayError,
    ProtectedPacket,
    RoiProtector,
    RoiReceiver,
)
from unoq_lorenz.protocol import (
    AEAD_ALGORITHM,
    KDF_PROFILE,
    PROTOCOL_VERSION,
    RUN_KEY_POLICY,
)
from unoq_lorenz.transform import LorenzTransformConfig


RUN_KEY = bytes(range(32))
RUN_ID = "host-20260720-a"
NONCE = bytes.fromhex("001122334455667700000000")


def _metadata(
    protector: RoiProtector,
    *,
    packet_id: int = 0,
    use_lorenz: bool = True,
):
    return protector.metadata(
        run_id=RUN_ID,
        packet_id=packet_id,
        frame_id=2,
        roi_id=0,
        x0=1,
        y0=2,
        x1=10,
        y1=10,
        height=8,
        width=9,
        channels=3,
        use_lorenz=use_lorenz,
    )


@pytest.mark.parametrize("use_lorenz", [False, True])
def test_aead_roi_round_trip(use_lorenz):
    roi = np.arange(8 * 9 * 3, dtype=np.uint16).astype(np.uint8).reshape(8, 9, 3)
    protector = RoiProtector(RUN_KEY)
    packet = protector.encrypt(
        roi,
        _metadata(protector, use_lorenz=use_lorenz),
        NONCE,
    )
    assert np.array_equal(protector.decrypt(packet), roi)


def test_packet_metadata_authenticates_complete_canonical_profile():
    protector = RoiProtector(RUN_KEY)
    metadata = _metadata(protector)
    assert metadata.run_id == RUN_ID
    assert metadata.packet_id == 0
    assert metadata.protocol_version == PROTOCOL_VERSION
    assert metadata.aead_algorithm == AEAD_ALGORITHM
    assert metadata.kdf_profile == KDF_PROFILE
    assert metadata.transform_version == protector.transform_version
    assert metadata.transform_profile == protector.transform_profile
    assert metadata.transform_profile_sha256 == protector.transform_profile_sha256
    assert metadata.computed_transform_profile_sha256() == protector.transform_profile_sha256
    assert protector.run_key_policy == RUN_KEY_POLICY


def test_packet_json_round_trip_preserves_recoverable_binary_payload():
    roi = np.arange(8 * 9 * 3, dtype=np.uint8).reshape(8, 9, 3)
    protector = RoiProtector(RUN_KEY)
    original = protector.encrypt(roi, _metadata(protector), NONCE)
    restored = ProtectedPacket.from_json(original.to_json())
    assert restored == original
    assert restored.nonce_prefix == NONCE[:8]
    assert restored.nonce_counter == original.metadata.packet_id
    assert restored.to_dict() == original.to_dict()
    assert np.array_equal(protector.decrypt(restored), roi)


def test_ciphertext_tampering_is_rejected():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    protector = RoiProtector(RUN_KEY)
    packet = protector.encrypt(roi, _metadata(protector), NONCE)
    tampered = bytearray(packet.ciphertext_and_tag)
    tampered[0] ^= 1
    bad_packet = ProtectedPacket(packet.metadata, packet.nonce, bytes(tampered))
    with pytest.raises(InvalidTag):
        protector.decrypt(bad_packet)


def test_encryption_rejects_packet_id_that_does_not_match_nonce_counter():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    protector = RoiProtector(RUN_KEY)
    with pytest.raises(ValueError, match="nonce counter"):
        protector.encrypt(roi, _metadata(protector, packet_id=1), NONCE)


def test_metadata_tampering_is_rejected_before_profile_interpretation():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    protector = RoiProtector(RUN_KEY)
    metadata = _metadata(protector)
    packet = protector.encrypt(roi, metadata, NONCE)
    altered = replace(metadata, frame_id=3)
    with pytest.raises(InvalidTag):
        protector.decrypt(
            ProtectedPacket(altered, packet.nonce, packet.ciphertext_and_tag)
        )


def test_authenticated_transform_profile_mismatch_is_explicitly_rejected():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    sender = RoiProtector(RUN_KEY)
    receiver = RoiProtector(
        RUN_KEY,
        transform_config=LorenzTransformConfig(dt=0.006),
    )
    packet = sender.encrypt(roi, _metadata(sender), NONCE)
    with pytest.raises(PacketProfileMismatch, match="transform"):
        receiver.decrypt(packet)


def test_receiver_rejects_replay_after_first_authenticated_delivery():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    protector = RoiProtector(RUN_KEY)
    packet = protector.encrypt(roi, _metadata(protector), NONCE)
    receiver = RoiReceiver(protector)
    assert np.array_equal(receiver.receive(packet), roi)
    with pytest.raises(PacketReplayError, match="already been accepted"):
        receiver.receive(packet)
    assert receiver.replay_guard.accepted_count == 1


def test_receiver_rejects_authenticated_nonce_reuse_across_run_ids():
    roi = np.zeros((8, 9, 3), dtype=np.uint8)
    protector = RoiProtector(RUN_KEY)
    first = protector.encrypt(roi, _metadata(protector, packet_id=0), NONCE)
    second_metadata = replace(
        _metadata(protector, packet_id=0),
        run_id="host-20260720-b",
    )
    second = protector.encrypt(roi, second_metadata, NONCE)
    receiver = RoiReceiver(protector)
    receiver.receive(first)
    with pytest.raises(PacketReplayError, match="nonce"):
        receiver.receive(second)

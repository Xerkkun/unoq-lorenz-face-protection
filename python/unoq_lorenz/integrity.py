"""Ephemeral integrity checks that do not retain source facial pixels."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

import numpy as np
from cryptography.exceptions import InvalidTag

from .packet import ProtectedPacket, RoiProtector


@dataclass(frozen=True)
class FrameIntegrityAudit:
    exact_recovery_checks: int
    exact_recovery_passes: int
    tamper_checks: int
    tamper_rejections: int


def audit_authenticated_frame(
    frame: np.ndarray,
    packets: Iterable[ProtectedPacket],
    *,
    protector: RoiProtector,
) -> FrameIntegrityAudit:
    """Compare recovered ROIs in memory and reject one modified copy per packet."""

    packet_tuple = tuple(packets)
    if not packet_tuple:
        raise ValueError("an authenticated frame audit requires at least one packet")

    exact_recovery_passes = 0
    tamper_rejections = 0
    for packet in packet_tuple:
        metadata = packet.metadata
        recovered = protector.decrypt(packet)
        source_roi = frame[
            metadata.y0 : metadata.y1,
            metadata.x0 : metadata.x1,
        ]
        if not np.array_equal(recovered, source_roi):
            raise RuntimeError(
                f"exact ROI recovery failed for packet {metadata.packet_id}"
            )
        exact_recovery_passes += 1

        changed = bytearray(packet.ciphertext_and_tag)
        changed[0] ^= 1
        tampered = replace(packet, ciphertext_and_tag=bytes(changed))
        try:
            protector.decrypt(tampered)
        except InvalidTag:
            tamper_rejections += 1
        else:
            raise RuntimeError(
                f"tampering was accepted for packet {metadata.packet_id}"
            )

    checked = len(packet_tuple)
    return FrameIntegrityAudit(
        exact_recovery_checks=checked,
        exact_recovery_passes=exact_recovery_passes,
        tamper_checks=checked,
        tamper_rejections=tamper_rejections,
    )

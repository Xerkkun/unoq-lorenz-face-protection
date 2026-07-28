"""Frame-level helpers that keep biometric pixels out of measurement logs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .nonce import NonceSequence
from .packet import ProtectedPacket, RoiMetadata, RoiProtector
from .protocol import validate_run_id


@dataclass(frozen=True)
class FrameProtectionResult:
    preview: np.ndarray
    packets: tuple[ProtectedPacket, ...]
    accepted_boxes: tuple[tuple[int, int, int, int], ...]


def _clamp_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = (int(value) for value in box)
    x0 = max(0, min(x0, width))
    y0 = max(0, min(y0, height))
    x1 = max(0, min(x1, width))
    y1 = max(0, min(y1, height))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def protect_frame(
    frame: np.ndarray,
    boxes: Iterable[tuple[int, int, int, int]],
    *,
    run_id: str,
    frame_id: int,
    protector: RoiProtector,
    nonces: NonceSequence,
    use_lorenz: bool,
) -> FrameProtectionResult:
    validate_run_id(run_id)
    if frame.dtype != np.uint8 or frame.ndim not in (2, 3):
        raise TypeError("frame must be a two- or three-dimensional uint8 array")
    height, width = frame.shape[:2]
    channels = 1 if frame.ndim == 2 else frame.shape[2]
    preview = frame.copy()
    packets: list[ProtectedPacket] = []
    accepted: list[tuple[int, int, int, int]] = []

    for roi_id, raw_box in enumerate(boxes):
        box = _clamp_box(raw_box, width, height)
        if box is None:
            continue
        x0, y0, x1, y1 = box
        roi = frame[y0:y1, x0:x1].copy()
        allocation = nonces.allocate()
        metadata: RoiMetadata = protector.metadata(
            run_id=run_id,
            packet_id=allocation.counter,
            frame_id=frame_id,
            roi_id=roi_id,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            height=y1 - y0,
            width=x1 - x0,
            channels=channels,
            use_lorenz=use_lorenz,
        )
        packet = protector.encrypt(roi, metadata, allocation.nonce)
        packets.append(packet)
        accepted.append(box)

        visible_bytes = packet.ciphertext_and_tag[: roi.size]
        preview[y0:y1, x0:x1] = np.frombuffer(
            visible_bytes, dtype=np.uint8
        ).reshape(roi.shape)

    return FrameProtectionResult(preview, tuple(packets), tuple(accepted))


def recover_frame(
    protected_preview: np.ndarray,
    packets: Iterable[ProtectedPacket],
    *,
    protector: RoiProtector,
) -> np.ndarray:
    recovered = protected_preview.copy()
    for packet in packets:
        metadata = packet.metadata
        roi = protector.decrypt(packet)
        recovered[metadata.y0 : metadata.y1, metadata.x0 : metadata.x1] = roi
    return recovered

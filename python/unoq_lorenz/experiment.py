"""Registered experiment modes for the UNO Q board campaign."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import cv2
import numpy as np

from .nonce import NonceSequence
from .packet import ProtectedPacket, RoiProtector
from .pipeline import FrameProtectionResult, _clamp_box, protect_frame


class ExperimentMode(str, Enum):
    M0_DETECTION = "M0_detection"
    M1_BLUR = "M1_blur"
    M2_LORENZ_ONLY = "M2_lorenz_only"
    M3_AEAD = "M3_aead"
    M4_LORENZ_AEAD = "M4_lorenz_aead"

    @property
    def is_authenticated(self) -> bool:
        return self in {self.M3_AEAD, self.M4_LORENZ_AEAD}

    @property
    def is_insecure_ablation(self) -> bool:
        return not self.is_authenticated


@dataclass(frozen=True)
class ExperimentFrameResult:
    preview: np.ndarray
    packets: tuple[ProtectedPacket, ...]
    accepted_boxes: tuple[tuple[int, int, int, int], ...]
    mode: ExperimentMode


def _accepted_boxes(
    boxes: Iterable[tuple[int, int, int, int]],
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], ...]:
    accepted = []
    for raw_box in boxes:
        box = _clamp_box(raw_box, width, height)
        if box is not None:
            accepted.append(box)
    return tuple(accepted)


def run_experiment_mode(
    frame: np.ndarray,
    boxes: Iterable[tuple[int, int, int, int]],
    *,
    run_id: str,
    frame_id: int,
    mode: ExperimentMode,
    protector: RoiProtector,
    nonces: NonceSequence,
    allow_insecure_ablation: bool = False,
) -> ExperimentFrameResult:
    """Process one frame under exactly one preregistered condition."""

    if frame.dtype != np.uint8 or frame.ndim not in (2, 3):
        raise TypeError("frame must be a two- or three-dimensional uint8 array")
    if mode.is_insecure_ablation and not allow_insecure_ablation:
        raise PermissionError(
            f"{mode.value} is not authenticated; set the laboratory opt-in"
        )

    height, width = frame.shape[:2]
    accepted = _accepted_boxes(boxes, width, height)

    if mode in {ExperimentMode.M3_AEAD, ExperimentMode.M4_LORENZ_AEAD}:
        protected: FrameProtectionResult = protect_frame(
            frame,
            accepted,
            run_id=run_id,
            frame_id=frame_id,
            protector=protector,
            nonces=nonces,
            use_lorenz=mode is ExperimentMode.M4_LORENZ_AEAD,
        )
        return ExperimentFrameResult(
            protected.preview,
            protected.packets,
            protected.accepted_boxes,
            mode,
        )

    preview = frame.copy()
    for x0, y0, x1, y1 in accepted:
        roi = frame[y0:y1, x0:x1]
        if mode is ExperimentMode.M0_DETECTION:
            continue
        if mode is ExperimentMode.M1_BLUR:
            preview[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (31, 31), 0)
            continue
        if mode is ExperimentMode.M2_LORENZ_ONLY:
            preview[y0:y1, x0:x1] = protector.transform_for_insecure_ablation(
                roi,
                nonces.next(),
            )
            continue
        raise AssertionError(f"unhandled experiment mode: {mode}")

    return ExperimentFrameResult(preview, (), accepted, mode)

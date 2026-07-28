import numpy as np
import pytest

from unoq_lorenz.experiment import ExperimentMode, run_experiment_mode
from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector


def _run(mode, *, allow=False):
    frame = np.arange(72 * 96 * 3, dtype=np.uint32).astype(np.uint8).reshape(72, 96, 3)
    return frame, run_experiment_mode(
        frame,
        [(8, 10, 48, 58)],
        run_id="experiment-20260720",
        frame_id=4,
        mode=mode,
        protector=RoiProtector(bytes(range(32))),
        nonces=NonceSequence(b"MODE2026"),
        allow_insecure_ablation=allow,
    )


@pytest.mark.parametrize(
    "mode",
    [
        ExperimentMode.M0_DETECTION,
        ExperimentMode.M1_BLUR,
        ExperimentMode.M2_LORENZ_ONLY,
    ],
)
def test_insecure_modes_require_explicit_opt_in(mode):
    with pytest.raises(PermissionError):
        _run(mode)


def test_detection_baseline_preserves_frame_only_with_opt_in():
    frame, result = _run(ExperimentMode.M0_DETECTION, allow=True)
    assert np.array_equal(result.preview, frame)
    assert result.packets == ()


@pytest.mark.parametrize(
    "mode",
    [ExperimentMode.M1_BLUR, ExperimentMode.M2_LORENZ_ONLY],
)
def test_visual_ablations_modify_only_accepted_roi(mode):
    frame, result = _run(mode, allow=True)
    assert not np.array_equal(result.preview[10:58, 8:48], frame[10:58, 8:48])
    assert np.array_equal(result.preview[:8], frame[:8])
    assert result.packets == ()


@pytest.mark.parametrize(
    "mode",
    [ExperimentMode.M3_AEAD, ExperimentMode.M4_LORENZ_AEAD],
)
def test_authenticated_modes_create_packets_without_insecure_opt_in(mode):
    frame, result = _run(mode)
    assert len(result.packets) == 1
    assert not np.array_equal(result.preview, frame)

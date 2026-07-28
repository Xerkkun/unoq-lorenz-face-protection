"""Platform-independent core for the UNO Q Lorenz ROI experiment."""

from .lorenz import LorenzParameters, lorenz_trajectory
from .nonce import NonceAllocation, NonceSequence
from .packet import (
    PacketProfileMismatch,
    PacketReplayError,
    ProtectedPacket,
    ReplayGuard,
    RoiMetadata,
    RoiProtector,
    RoiReceiver,
)
from .pipeline import FrameProtectionResult, protect_frame, recover_frame
from .packet_store import PacketStore, StoredFrameBundle, load_frame_bundle
from .protocol import AEAD_ALGORITHM, KDF_PROFILE, PROTOCOL_VERSION, RUN_KEY_POLICY
from .run_key import RunKeyMaterial, load_or_create_run_key
from .telemetry import TelemetryDispatcher, TelemetrySample
from .transform import LorenzTransform, LorenzTransformConfig
from .experiment import ExperimentFrameResult, ExperimentMode, run_experiment_mode

__all__ = [
    "FrameProtectionResult",
    "ExperimentFrameResult",
    "ExperimentMode",
    "LorenzParameters",
    "LorenzTransform",
    "LorenzTransformConfig",
    "NonceAllocation",
    "NonceSequence",
    "PacketProfileMismatch",
    "PacketReplayError",
    "PacketStore",
    "ProtectedPacket",
    "ReplayGuard",
    "RoiMetadata",
    "RoiProtector",
    "RoiReceiver",
    "RunKeyMaterial",
    "StoredFrameBundle",
    "TelemetryDispatcher",
    "TelemetrySample",
    "AEAD_ALGORITHM",
    "KDF_PROFILE",
    "PROTOCOL_VERSION",
    "RUN_KEY_POLICY",
    "lorenz_trajectory",
    "load_frame_bundle",
    "load_or_create_run_key",
    "protect_frame",
    "recover_frame",
    "run_experiment_mode",
]

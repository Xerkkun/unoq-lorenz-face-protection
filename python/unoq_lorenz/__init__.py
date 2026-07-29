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
from .laptop_sink import (
    LaptopBundleDispatcher,
    ReceivedBundleStore,
    load_receiver_token,
)
from .packet_store import (
    FrameBundleInfo,
    PacketStore,
    StoredFrameBundle,
    load_frame_bundle,
    parse_frame_bundle_bytes,
)
from .protocol import AEAD_ALGORITHM, KDF_PROFILE, PROTOCOL_VERSION, RUN_KEY_POLICY
from .run_key import RunKeyMaterial, load_or_create_run_key
from .telemetry import TelemetryDispatcher, TelemetrySample
from .transform import LorenzTransform, LorenzTransformConfig
from .experiment import ExperimentFrameResult, ExperimentMode, run_experiment_mode

__all__ = [
    "FrameProtectionResult",
    "FrameBundleInfo",
    "ExperimentFrameResult",
    "ExperimentMode",
    "LorenzParameters",
    "LorenzTransform",
    "LorenzTransformConfig",
    "LaptopBundleDispatcher",
    "NonceAllocation",
    "NonceSequence",
    "PacketProfileMismatch",
    "PacketReplayError",
    "PacketStore",
    "ProtectedPacket",
    "ReplayGuard",
    "ReceivedBundleStore",
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
    "load_receiver_token",
    "load_or_create_run_key",
    "parse_frame_bundle_bytes",
    "protect_frame",
    "recover_frame",
    "run_experiment_mode",
]

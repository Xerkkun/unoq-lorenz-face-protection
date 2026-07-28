"""Authenticated packet representation for one protected facial ROI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .kdf import derive_experiment_subkeys
from .protocol import (
    AEAD_ALGORITHM,
    KDF_PROFILE,
    PROTOCOL_VERSION,
    RUN_KEY_POLICY,
    validate_run_id,
)
from .transform import LorenzTransform, LorenzTransformConfig


class PacketProfileMismatch(ValueError):
    """An authenticated packet does not match the local protocol profile."""


class PacketReplayError(ValueError):
    """A valid packet identity or nonce has already been accepted."""


@dataclass(frozen=True)
class RoiMetadata:
    run_id: str
    packet_id: int
    frame_id: int
    roi_id: int
    x0: int
    y0: int
    x1: int
    y1: int
    height: int
    width: int
    channels: int
    use_lorenz: bool
    transform_version: str
    transform_profile: str
    transform_profile_sha256: str
    aead_algorithm: str = AEAD_ALGORITHM
    kdf_profile: str = KDF_PROFILE
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        integer_values = (
            self.packet_id,
            self.frame_id,
            self.roi_id,
            self.x0,
            self.y0,
            self.x1,
            self.y1,
            self.height,
            self.width,
            self.channels,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in integer_values
        ):
            raise TypeError("ROI metadata counters, coordinates, and shape must be integers")
        if not 0 <= self.packet_id < 2**32:
            raise ValueError("packet_id is outside uint32 range")
        if min(self.frame_id, self.roi_id, self.x0, self.y0) < 0:
            raise ValueError("frame, ROI, and coordinates must be non-negative")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("ROI coordinates are empty or reversed")
        if self.height != self.y1 - self.y0 or self.width != self.x1 - self.x0:
            raise ValueError("metadata shape does not match ROI coordinates")
        if self.channels not in (1, 3, 4):
            raise ValueError(
                "only one-, three-, and four-channel uint8 ROIs are supported"
            )
        if not isinstance(self.use_lorenz, bool):
            raise TypeError("use_lorenz must be boolean")
        for name, value in (
            ("transform_version", self.transform_version),
            ("transform_profile", self.transform_profile),
            ("aead_algorithm", self.aead_algorithm),
            ("kdf_profile", self.kdf_profile),
            ("protocol_version", self.protocol_version),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must not be empty")
        if (
            not isinstance(self.transform_profile_sha256, str)
            or len(self.transform_profile_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.transform_profile_sha256
            )
        ):
            raise ValueError("transform_profile_sha256 must be lowercase SHA-256 hex")

    def canonical_aad(self) -> bytes:
        """Return canonical UTF-8 AAD containing every metadata field."""

        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

    def computed_transform_profile_sha256(self) -> str:
        return hashlib.sha256(self.transform_profile.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProtectedPacket:
    metadata: RoiMetadata
    nonce: bytes
    ciphertext_and_tag: bytes

    def __post_init__(self) -> None:
        try:
            nonce = bytes(self.nonce)
            ciphertext_and_tag = bytes(self.ciphertext_and_tag)
        except (TypeError, ValueError) as error:
            raise TypeError("nonce and ciphertext_and_tag must be bytes-like") from error
        if len(nonce) != 12:
            raise ValueError("packet nonce must contain exactly 12 bytes")
        if len(ciphertext_and_tag) < 16:
            raise ValueError("ciphertext_and_tag is shorter than the AEAD tag")
        object.__setattr__(self, "nonce", nonce)
        object.__setattr__(self, "ciphertext_and_tag", ciphertext_and_tag)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-compatible persistence representation."""

        return {
            "metadata": asdict(self.metadata),
            "nonce_b64": base64.b64encode(self.nonce).decode("ascii"),
            "ciphertext_and_tag_b64": base64.b64encode(
                self.ciphertext_and_tag
            ).decode("ascii"),
        }

    @property
    def nonce_prefix(self) -> bytes:
        return self.nonce[:8]

    @property
    def nonce_counter(self) -> int:
        return int.from_bytes(self.nonce[8:], "big")

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtectedPacket":
        if not isinstance(payload, Mapping):
            raise TypeError("packet payload must be a mapping")
        try:
            metadata_payload = payload["metadata"]
            nonce_b64 = payload["nonce_b64"]
            ciphertext_b64 = payload["ciphertext_and_tag_b64"]
        except KeyError as error:
            raise ValueError(f"packet payload is missing {error.args[0]}") from error
        if not isinstance(metadata_payload, Mapping):
            raise TypeError("packet metadata must be a mapping")
        if not isinstance(nonce_b64, str) or not isinstance(ciphertext_b64, str):
            raise TypeError("packet binary fields must use base64 strings")
        return cls(
            metadata=RoiMetadata(**dict(metadata_payload)),
            nonce=base64.b64decode(nonce_b64, validate=True),
            ciphertext_and_tag=base64.b64decode(ciphertext_b64, validate=True),
        )

    @classmethod
    def from_json(cls, payload: str | bytes | bytearray) -> "ProtectedPacket":
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            raise ValueError("packet JSON is invalid") from error
        return cls.from_dict(decoded)


class RoiProtector:
    """Protect and recover ROIs under a fresh 256-bit experiment run key."""

    def __init__(
        self,
        run_key: bytes,
        *,
        transform_config: LorenzTransformConfig = LorenzTransformConfig(),
    ) -> None:
        aead_key, lorenz_key = derive_experiment_subkeys(run_key)
        self._aead = ChaCha20Poly1305(aead_key)
        self._lorenz = LorenzTransform(lorenz_key, transform_config)
        self._transform_profile = transform_config.canonical_profile_json()
        self._transform_profile_sha256 = transform_config.profile_sha256

    @property
    def aead_algorithm(self) -> str:
        return AEAD_ALGORITHM

    @property
    def kdf_profile(self) -> str:
        return KDF_PROFILE

    @property
    def run_key_policy(self) -> str:
        return RUN_KEY_POLICY

    @property
    def transform_version(self) -> str:
        return self._lorenz.config.version

    @property
    def transform_profile(self) -> str:
        return self._transform_profile

    @property
    def transform_profile_sha256(self) -> str:
        return self._transform_profile_sha256

    def metadata(
        self,
        *,
        run_id: str,
        packet_id: int,
        frame_id: int,
        roi_id: int,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        height: int,
        width: int,
        channels: int,
        use_lorenz: bool,
    ) -> RoiMetadata:
        """Build metadata bound to this protector's exact local profile."""

        return RoiMetadata(
            run_id=run_id,
            packet_id=packet_id,
            frame_id=frame_id,
            roi_id=roi_id,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            height=height,
            width=width,
            channels=channels,
            use_lorenz=use_lorenz,
            transform_version=self.transform_version,
            transform_profile=self.transform_profile,
            transform_profile_sha256=self.transform_profile_sha256,
        )

    def _require_local_profile(self, metadata: RoiMetadata) -> None:
        actual_hash = metadata.computed_transform_profile_sha256()
        if not hmac.compare_digest(actual_hash, metadata.transform_profile_sha256):
            raise PacketProfileMismatch(
                "authenticated transform profile does not match its SHA-256"
            )
        expected = {
            "protocol_version": PROTOCOL_VERSION,
            "aead_algorithm": AEAD_ALGORITHM,
            "kdf_profile": KDF_PROFILE,
            "transform_version": self.transform_version,
            "transform_profile": self.transform_profile,
            "transform_profile_sha256": self.transform_profile_sha256,
        }
        actual = {
            "protocol_version": metadata.protocol_version,
            "aead_algorithm": metadata.aead_algorithm,
            "kdf_profile": metadata.kdf_profile,
            "transform_version": metadata.transform_version,
            "transform_profile": metadata.transform_profile,
            "transform_profile_sha256": metadata.transform_profile_sha256,
        }
        for name, expected_value in expected.items():
            if not hmac.compare_digest(
                actual[name].encode("utf-8"),
                expected_value.encode("utf-8"),
            ):
                raise PacketProfileMismatch(
                    f"authenticated packet {name} does not match the local profile"
                )

    def encrypt(
        self,
        roi: np.ndarray,
        metadata: RoiMetadata,
        nonce: bytes,
    ) -> ProtectedPacket:
        if roi.dtype != np.uint8:
            raise TypeError("ROI must use uint8 samples")
        expected_shape = (
            (metadata.height, metadata.width)
            if metadata.channels == 1
            else (metadata.height, metadata.width, metadata.channels)
        )
        if roi.shape != expected_shape:
            raise ValueError(f"ROI shape {roi.shape} does not match {expected_shape}")
        if len(nonce) != 12:
            raise ValueError("ChaCha20-Poly1305 nonce must contain 12 bytes")
        if metadata.packet_id != int.from_bytes(nonce[8:], "big"):
            raise ValueError("packet_id must match the uint32 nonce counter")
        self._require_local_profile(metadata)

        plaintext = np.ascontiguousarray(roi).tobytes()
        protected_input = (
            self._lorenz.forward(plaintext, nonce)
            if metadata.use_lorenz
            else plaintext
        )
        ciphertext_and_tag = self._aead.encrypt(
            nonce,
            protected_input,
            metadata.canonical_aad(),
        )
        return ProtectedPacket(metadata, bytes(nonce), ciphertext_and_tag)

    def transform_for_insecure_ablation(
        self,
        roi: np.ndarray,
        nonce: bytes,
    ) -> np.ndarray:
        """Return the unauthenticated Lorenz-only preview for condition M2."""

        if roi.dtype != np.uint8:
            raise TypeError("ROI must use uint8 samples")
        if len(nonce) != 12:
            raise ValueError("nonce must contain 12 bytes")
        contiguous = np.ascontiguousarray(roi)
        transformed = self._lorenz.forward(contiguous.tobytes(), nonce)
        return np.frombuffer(transformed, dtype=np.uint8).reshape(roi.shape).copy()

    def decrypt(self, packet: ProtectedPacket) -> np.ndarray:
        """Authenticate, validate the profile, and then invert the transform."""

        metadata = packet.metadata
        transformed = self._aead.decrypt(
            packet.nonce,
            packet.ciphertext_and_tag,
            metadata.canonical_aad(),
        )
        self._require_local_profile(metadata)
        if metadata.packet_id != packet.nonce_counter:
            raise ValueError(
                "authenticated packet_id does not match the uint32 nonce counter"
            )
        plaintext = (
            self._lorenz.inverse(transformed, packet.nonce)
            if metadata.use_lorenz
            else transformed
        )
        shape = (
            (metadata.height, metadata.width)
            if metadata.channels == 1
            else (metadata.height, metadata.width, metadata.channels)
        )
        expected_bytes = metadata.height * metadata.width * metadata.channels
        if len(plaintext) != expected_bytes:
            raise ValueError("authenticated ROI length does not match metadata")
        return np.frombuffer(plaintext, dtype=np.uint8).reshape(shape).copy()


class ReplayGuard:
    """Thread-safe acceptance ledger for one receiver/run-key lifetime."""

    def __init__(self) -> None:
        self._packet_ids: set[tuple[str, int]] = set()
        self._nonces: set[bytes] = set()
        self._lock = threading.Lock()

    def accept(self, packet: ProtectedPacket) -> None:
        identity = (packet.metadata.run_id, packet.metadata.packet_id)
        with self._lock:
            if identity in self._packet_ids:
                raise PacketReplayError(
                    "authenticated run_id/packet_id has already been accepted"
                )
            if packet.nonce in self._nonces:
                raise PacketReplayError(
                    "authenticated nonce has already been accepted under this run key"
                )
            self._packet_ids.add(identity)
            self._nonces.add(packet.nonce)

    @property
    def accepted_count(self) -> int:
        with self._lock:
            return len(self._packet_ids)


class RoiReceiver:
    """Stateful authenticated receiver that rejects packet replays."""

    def __init__(
        self,
        protector: RoiProtector,
        *,
        replay_guard: ReplayGuard | None = None,
    ) -> None:
        self._protector = protector
        self.replay_guard = replay_guard or ReplayGuard()

    def receive(self, packet: ProtectedPacket) -> np.ndarray:
        roi = self._protector.decrypt(packet)
        self.replay_guard.accept(packet)
        return roi

    def decrypt(self, packet: ProtectedPacket) -> np.ndarray:
        return self.receive(packet)

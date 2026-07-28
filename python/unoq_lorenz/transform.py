"""Reversible Lorenz permutation--diffusion transform under evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass

import numpy as np

from .kdf import hkdf_sha256
from .lorenz import LorenzParameters, lorenz_trajectory


@dataclass(frozen=True)
class LorenzTransformConfig:
    parameters: LorenzParameters = LorenzParameters()
    dt: float = 0.005
    burn_in: int = 2_048
    seed_samples: int = 512
    quantization_scale: float = 1_000_000_000.0
    version: str = "lorenz-rk4-sha256-pcg64-v2"

    def __post_init__(self) -> None:
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError("dt must be positive")
        if self.burn_in < 0:
            raise ValueError("burn_in must be non-negative")
        if self.seed_samples <= 0:
            raise ValueError("seed_samples must be positive")
        if (
            not math.isfinite(self.quantization_scale)
            or self.quantization_scale <= 0.0
        ):
            raise ValueError("quantization_scale must be positive")
        if not self.version:
            raise ValueError("transform version must not be empty")
        try:
            self.version.encode("ascii")
        except UnicodeEncodeError as error:
            raise ValueError("transform version must contain only ASCII") from error
        if not all(
            math.isfinite(value)
            for value in (
                self.parameters.sigma,
                self.parameters.rho,
                self.parameters.beta,
            )
        ):
            raise ValueError("Lorenz parameters must be finite")

    @staticmethod
    def _canonical_float(value: float) -> str:
        """Return an exact, platform-stable representation of a binary64."""

        return float(value).hex()

    def canonical_profile_dict(self) -> dict[str, object]:
        """Return every input that defines the v2 reversible schedule."""

        return {
            "burn_in": self.burn_in,
            "dt_binary64": self._canonical_float(self.dt),
            "integrator": "fixed-step-rk4-float64",
            "lorenz_parameters_binary64": {
                "beta": self._canonical_float(self.parameters.beta),
                "rho": self._canonical_float(self.parameters.rho),
                "sigma": self._canonical_float(self.parameters.sigma),
            },
            "mask_and_permutation_expander": "numpy-pcg64",
            "numpy_runtime_version": np.__version__,
            "numpy_schedule_api": "Generator(PCG64).permutation+integers",
            "profile_schema": "unoq-lorenz-transform-profile-v1",
            "quantization": "rint-to-little-endian-int64",
            "quantization_scale_binary64": self._canonical_float(
                self.quantization_scale
            ),
            "schedule_digest": "sha256",
            "schedule_kdf": "hkdf-sha256",
            "seed_samples": self.seed_samples,
            "seed_width_bits": 128,
            "version": self.version,
        }

    def canonical_profile_json(self) -> str:
        """Serialize the complete transform profile canonically."""

        return json.dumps(
            self.canonical_profile_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @property
    def profile_sha256(self) -> str:
        return hashlib.sha256(
            self.canonical_profile_json().encode("ascii")
        ).hexdigest()


class LorenzTransform:
    """Generate a deterministic schedule from a separated key and nonce.

    This transform is a research variable, not a security boundary. Its output
    is always placed inside an authenticated-encryption envelope.
    """

    def __init__(
        self,
        schedule_key: bytes,
        config: LorenzTransformConfig = LorenzTransformConfig(),
    ) -> None:
        if len(schedule_key) != 32:
            raise ValueError("Lorenz schedule key must contain 32 bytes")
        self._key = bytes(schedule_key)
        self.config = config
        self._lorenz_master_digest = self._compute_lorenz_master_digest()

    @staticmethod
    def _map_uint64(value: int, low: float, high: float) -> float:
        fraction = value / float(2**64 - 1)
        return low + fraction * (high - low)

    def _initial_state(self, nonce: bytes) -> tuple[float, float, float]:
        if len(nonce) != 12:
            raise ValueError("nonce must contain exactly 12 bytes")
        material = hkdf_sha256(
            self._key,
            salt=nonce,
            info=(self.config.version + "/initial-state").encode("ascii"),
            length=24,
        )
        values = [
            int.from_bytes(material[offset : offset + 8], "big")
            for offset in (0, 8, 16)
        ]
        return (
            self._map_uint64(values[0], -15.0, 15.0),
            self._map_uint64(values[1], -20.0, 20.0),
            self._map_uint64(values[2], 5.0, 35.0),
        )

    def _compute_lorenz_master_digest(self) -> bytes:
        """Integrate and canonicalize Lorenz once per experiment key."""

        states = lorenz_trajectory(
            self._initial_state(bytes(12)),
            self.config.seed_samples,
            dt=self.config.dt,
            burn_in=self.config.burn_in,
            parameters=self.config.parameters,
        )
        quantized = np.rint(states * self.config.quantization_scale).astype("<i8")
        return hashlib.sha256(quantized.tobytes(order="C")).digest()

    def _seed(self, nonce: bytes, length: int) -> bytes:
        """Derive a fixed-cost deterministic schedule seed."""

        info = (
            self.config.version.encode("ascii")
            + b"/schedule/"
            + struct.pack(">Q", length)
            + self._lorenz_master_digest
        )
        return hkdf_sha256(
            self._key,
            salt=nonce,
            info=info,
            length=32,
        )

    def schedule(self, nonce: bytes, length: int) -> tuple[np.ndarray, np.ndarray]:
        if length < 0:
            raise ValueError("length must be non-negative")
        if length == 0:
            empty = np.empty(0, dtype=np.int64)
            return empty, np.empty(0, dtype=np.uint8)

        seed = self._seed(nonce, length)
        generator = np.random.Generator(
            np.random.PCG64(int.from_bytes(seed[:16], "big"))
        )
        permutation = generator.permutation(length).astype(np.int64, copy=False)
        mask = generator.integers(0, 256, size=length, dtype=np.uint8)
        return permutation, mask

    def forward(self, plaintext: bytes, nonce: bytes) -> bytes:
        values = np.frombuffer(plaintext, dtype=np.uint8)
        permutation, mask = self.schedule(nonce, len(values))
        return np.bitwise_xor(values[permutation], mask).tobytes()

    def inverse(self, transformed: bytes, nonce: bytes) -> bytes:
        values = np.frombuffer(transformed, dtype=np.uint8)
        permutation, mask = self.schedule(nonce, len(values))
        permuted_plaintext = np.bitwise_xor(values, mask)
        plaintext = np.empty_like(permuted_plaintext)
        plaintext[permutation] = permuted_plaintext
        return plaintext.tobytes()

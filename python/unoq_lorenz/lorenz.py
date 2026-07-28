"""Deterministic fixed-step integration of the classical Lorenz system."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LorenzParameters:
    sigma: float = 10.0
    rho: float = 28.0
    beta: float = 8.0 / 3.0


def lorenz_rhs(state: np.ndarray, parameters: LorenzParameters) -> np.ndarray:
    x, y, z = state
    return np.asarray(
        [
            parameters.sigma * (y - x),
            x * (parameters.rho - z) - y,
            x * y - parameters.beta * z,
        ],
        dtype=np.float64,
    )


def rk4_step(
    state: np.ndarray,
    dt: float,
    parameters: LorenzParameters,
) -> np.ndarray:
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    k1 = lorenz_rhs(state, parameters)
    k2 = lorenz_rhs(state + 0.5 * dt * k1, parameters)
    k3 = lorenz_rhs(state + 0.5 * dt * k2, parameters)
    k4 = lorenz_rhs(state + dt * k3, parameters)
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def lorenz_trajectory(
    initial_state: tuple[float, float, float] | np.ndarray,
    samples: int,
    *,
    dt: float = 0.005,
    burn_in: int = 1_024,
    parameters: LorenzParameters = LorenzParameters(),
) -> np.ndarray:
    """Return ``samples`` post-transient states as float64 values."""

    if samples < 0:
        raise ValueError("samples must be non-negative")
    if burn_in < 0:
        raise ValueError("burn_in must be non-negative")
    state = np.asarray(initial_state, dtype=np.float64).reshape(3)
    if not np.isfinite(state).all():
        raise ValueError("initial state must be finite")

    for _ in range(burn_in):
        state = rk4_step(state, dt, parameters)

    result = np.empty((samples, 3), dtype=np.float64)
    for index in range(samples):
        state = rk4_step(state, dt, parameters)
        result[index] = state
    return result

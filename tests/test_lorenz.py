import numpy as np

from unoq_lorenz.lorenz import lorenz_trajectory


def test_lorenz_trajectory_is_reproducible_and_finite():
    first = lorenz_trajectory((1.0, 1.0, 1.0), 500, burn_in=100)
    second = lorenz_trajectory((1.0, 1.0, 1.0), 500, burn_in=100)
    assert np.array_equal(first, second)
    assert np.isfinite(first).all()


def test_nearby_initial_conditions_separate():
    first = lorenz_trajectory((1.0, 1.0, 1.0), 6_000, burn_in=0)
    second = lorenz_trajectory((1.0 + 1e-9, 1.0, 1.0), 6_000, burn_in=0)
    separation = np.linalg.norm(first - second, axis=1)
    # A single final-time comparison is fragile because two chaotic
    # trajectories can approach each other again.  The finite-horizon maximum
    # directly checks that the specified perturbation becomes observable.
    assert separation.max() > 1e-3

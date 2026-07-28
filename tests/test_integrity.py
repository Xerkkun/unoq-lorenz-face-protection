from __future__ import annotations

import numpy as np
import pytest

from unoq_lorenz.integrity import audit_authenticated_frame
from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.pipeline import protect_frame


def test_inline_integrity_audit_compares_source_and_rejects_tampering() -> None:
    frame = np.arange(48 * 64 * 3, dtype=np.uint32).astype(np.uint8).reshape(48, 64, 3)
    protector = RoiProtector(bytes(range(32)))
    protected = protect_frame(
        frame,
        [(4, 5, 30, 32), (35, 8, 58, 40)],
        run_id="inline-audit-20260728",
        frame_id=7,
        protector=protector,
        nonces=NonceSequence(b"AUDIT001"),
        use_lorenz=True,
    )

    result = audit_authenticated_frame(
        frame,
        protected.packets,
        protector=protector,
    )

    assert result.exact_recovery_checks == 2
    assert result.exact_recovery_passes == 2
    assert result.tamper_checks == 2
    assert result.tamper_rejections == 2


def test_inline_integrity_audit_requires_authenticated_packets() -> None:
    with pytest.raises(ValueError, match="at least one packet"):
        audit_authenticated_frame(
            np.zeros((4, 4, 3), dtype=np.uint8),
            (),
            protector=RoiProtector(bytes(range(32))),
        )

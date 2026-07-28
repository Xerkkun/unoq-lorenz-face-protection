import numpy as np

from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.pipeline import protect_frame, recover_frame


def test_frame_round_trip_and_unique_nonces():
    rng = np.random.default_rng(20260720)
    frame = rng.integers(0, 256, size=(72, 96, 3), dtype=np.uint8)
    protector = RoiProtector(bytes(range(32)))
    result = protect_frame(
        frame,
        [(8, 10, 40, 52), (50, 12, 88, 60)],
        run_id="pipeline-20260720",
        frame_id=7,
        protector=protector,
        nonces=NonceSequence(b"TEST2026"),
        use_lorenz=True,
    )
    assert not np.array_equal(result.preview, frame)
    recovered = recover_frame(result.preview, result.packets, protector=protector)
    assert np.array_equal(recovered, frame)
    assert len({packet.nonce for packet in result.packets}) == len(result.packets)
    assert [packet.metadata.packet_id for packet in result.packets] == [0, 1]
    assert {
        packet.metadata.run_id for packet in result.packets
    } == {"pipeline-20260720"}

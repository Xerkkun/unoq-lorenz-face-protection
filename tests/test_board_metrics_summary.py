from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.summarize_board_metrics import summarize, write_outputs


def _current_row(frame_id: int, timestamp: float) -> dict[str, str]:
    return {
        "run_id": "run-01",
        "condition": "M4_lorenz_aead",
        "scene": "synthetic-two-faces",
        "input_width": "640",
        "input_height": "480",
        "channels": "3",
        "frame_id": str(frame_id),
        "roi_count": "1",
        "roi_spatial_pixels": "100",
        "roi_bytes": "300",
        "preview_jpeg_bytes": "1000",
        "packet_count": "1",
        "packet_bytes": "400",
        "timestamp_monotonic_s": str(timestamp),
        "decode_ms": "2",
        "protect_ms": "3",
        "packet_store_ms": "1",
        "preview_encode_ms": "4",
        "callback_core_ms": "10",
        "source_order": str(frame_id),
        "source_csv": "run-01.csv",
    }


def test_current_schema_groups_and_derives_timestamped_rates() -> None:
    result = summarize(
        [_current_row(0, 10.0), _current_row(1, 10.5), _current_row(2, 11.0)]
    )

    assert len(result) == 1
    record = result[0]
    assert record["run_id"] == "run-01"
    assert record["resolution"] == "640x480"
    assert record["scene"] == "synthetic-two-faces"
    assert record["preview_output_fps"] == pytest.approx(2.0)
    assert record["protected_output_fps"] == pytest.approx(2.0)
    assert record["preview_throughput_bytes_s"] == pytest.approx(2000.0)
    assert record["protected_payload_throughput_bytes_s"] == pytest.approx(800.0)
    assert record["median_roi_spatial_pixels"] == 100.0
    assert record["median_roi_bytes"] == 300.0


def test_legacy_roi_samples_are_not_relabelled_as_spatial_pixels() -> None:
    legacy = {
        "frame_id": "0",
        "condition": "M4_lorenz_aead",
        "roi_count": "1",
        "roi_pixels": "300",
        "input_pixels": "307200",
        "output_jpeg_bytes": "1000",
        "decode_ms": "2",
        "protect_ms": "3",
        "encode_ms": "4",
        "callback_total_ms": "9",
        "source_csv": "legacy-run.csv",
        "source_order": "0",
    }

    record = summarize([legacy])[0]

    assert record["run_id"] == "legacy-run"
    assert record["legacy_rows"] == 1
    assert record["median_roi_spatial_pixels"] is None
    assert record["median_roi_bytes"] == 300.0
    assert record["median_preview_encode_ms"] == 4.0
    assert record["median_callback_core_ms"] == 9.0
    assert record["protected_output_fps"] is None


def test_rates_are_unavailable_for_non_increasing_monotonic_time() -> None:
    result = summarize([_current_row(0, 10.0), _current_row(1, 10.0)])[0]

    assert result["preview_output_fps"] is None
    assert result["protected_output_fps"] is None
    assert result["preview_rate_status"] == "unavailable_non_increasing_timestamps"
    assert result["protected_rate_status"] == "unavailable_non_increasing_timestamps"


def test_writes_machine_readable_summary_and_latency_figure() -> None:
    summary = summarize([_current_row(0, 10.0), _current_row(1, 10.5)])
    with TemporaryDirectory(prefix=".unoq-board-summary-test-", dir=Path.cwd()) as raw:
        root = Path(raw)
        output_dir = root / "data"
        figure_dir = root / "figures"

        write_outputs(summary, output_dir, figure_dir)

        assert (output_dir / "unoq_board_summary.json").is_file()
        assert (output_dir / "unoq_board_summary.csv").is_file()
        assert (figure_dir / "unoq_board_latency.png").stat().st_size > 0

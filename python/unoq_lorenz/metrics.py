"""Non-biometric frame metrics for the planned UNO Q campaign.

The schema distinguishes spatial pixels, byte samples, preview bytes, and
recoverable packet bytes so that comparisons keep compatible units.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrameMetrics:
    run_id: str
    scene: str
    timestamp_utc: str
    timestamp_monotonic_s: float
    frame_id: int
    condition: str
    input_width: int
    input_height: int
    channels: int
    bbox_margin_fraction: float
    roi_count: int
    roi_spatial_pixels: int
    roi_bytes: int
    input_jpeg_bytes: int
    preview_jpeg_bytes: int
    packet_count: int
    packet_bytes: int
    decode_ms: float
    protect_ms: float
    packet_store_ms: float
    inline_integrity_audit_enabled: int
    exact_recovery_checks: int
    exact_recovery_passes: int
    tamper_checks: int
    tamper_rejections: int
    integrity_audit_ms: float
    preview_encode_ms: float
    callback_core_ms: float
    process_cpu_percent: float
    process_rss_kib: int
    system_memory_percent: float
    source_dropped_callbacks: int
    source_frame_id_available: int
    telemetry_enqueued: int


FIELDNAMES = tuple(FrameMetrics.__dataclass_fields__)


def append_metrics(path: str | Path, metrics: FrameMetrics) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_header = not destination.exists()
    if not write_header:
        with destination.open("r", newline="", encoding="utf-8") as handle:
            existing_header = tuple(next(csv.reader(handle), ()))
        if existing_header != FIELDNAMES:
            raise ValueError(
                "metrics CSV schema mismatch; start a new run/file instead of "
                "appending incompatible rows"
            )
    with destination.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(asdict(metrics))

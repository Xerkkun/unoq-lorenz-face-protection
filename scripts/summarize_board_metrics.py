"""Summarize physical UNO Q CSV files without mixing in host verification.

The current schema keeps spatial pixels, byte counts, preview JPEGs, and
authenticated packets separate. A legacy CSV can still be read, but its old
``roi_pixels`` column is treated as a byte/sample count unless a channel count
is also available; it is never silently relabelled as spatial area.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np


BASE_REQUIRED_FIELDS = {"frame_id", "condition", "roi_count"}
MISSING_VALUES = {"", "na", "n/a", "nan", "none", "null", "unavailable"}
TIMING_ALIASES = {
    "decode_ms": ("decode_ms",),
    "protect_ms": ("protect_ms",),
    "packet_store_ms": ("packet_store_ms",),
    "integrity_audit_ms": ("integrity_audit_ms",),
    "preview_encode_ms": ("preview_encode_ms", "encode_ms"),
    "callback_core_ms": ("callback_core_ms", "callback_total_ms"),
}
RESOURCE_ALIASES = {
    "process_cpu_percent": ("process_cpu_percent",),
    "process_rss_kib": ("process_rss_kib",),
    "system_memory_percent": ("system_memory_percent",),
}


def expand_inputs(patterns: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for pattern in patterns:
        if any(marker in pattern.name for marker in ("*", "?", "[")):
            matches = sorted(pattern.parent.glob(pattern.name))
            if not matches:
                raise FileNotFoundError(f"input pattern matched no files: {pattern}")
            expanded.extend(matches)
        else:
            expanded.append(pattern)
    return expanded


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source_order = 0
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = BASE_REQUIRED_FIELDS.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{path} lacks required columns: {sorted(missing)}")
            for source_line, row in enumerate(reader, start=2):
                row["source_csv"] = str(path)
                row["source_line"] = str(source_line)
                row["source_order"] = str(source_order)
                source_order += 1
                rows.append(row)
    if not rows:
        raise ValueError("no board rows were found")
    return rows


def _first(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        raw = row.get(name)
        if raw is None:
            continue
        value = str(raw).strip()
        if value.lower() not in MISSING_VALUES:
            return value
    return None


def _where(row: dict[str, str]) -> str:
    return f"{row.get('source_csv', '<memory>')}:{row.get('source_line', '?')}"


def _number(
    row: dict[str, str],
    *names: str,
    required: bool = False,
) -> float | None:
    raw = _first(row, *names)
    if raw is None:
        if required:
            raise ValueError(f"{_where(row)} lacks a value for {names[0]}")
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{_where(row)} has invalid {names[0]}={raw!r}") from error
    if not math.isfinite(value):
        raise ValueError(f"{_where(row)} has non-finite {names[0]}={raw!r}")
    return value


def _integer(
    row: dict[str, str],
    *names: str,
    required: bool = False,
) -> int | None:
    value = _number(row, *names, required=required)
    if value is None:
        return None
    if not value.is_integer():
        raise ValueError(f"{_where(row)} has non-integral {names[0]}={value}")
    return int(value)


def _nonnegative(value: float | int | None, field: str, row: dict[str, str]) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{_where(row)} has negative {field}={value}")


def _resolution(row: dict[str, str], width: int | None, height: int | None) -> str:
    if width is not None and height is not None and width > 0 and height > 0:
        return f"{width}x{height}"
    declared = _first(row, "resolution", "input_resolution")
    if declared is not None:
        return declared
    input_pixels = _integer(row, "input_pixels")
    if input_pixels is not None:
        return f"unknown_shape_{input_pixels}_spatial_pixels"
    return "unknown"


def _normalise_row(row: dict[str, str]) -> dict[str, float | int | str | None]:
    condition = _first(row, "condition")
    if condition is None:
        raise ValueError(f"{_where(row)} has an empty condition")

    frame_id = _integer(row, "frame_id", required=True)
    roi_count = _integer(row, "roi_count", required=True)
    width = _integer(row, "input_width", "width")
    height = _integer(row, "input_height", "height")
    channels = _integer(row, "channels")
    for field, value in (
        ("frame_id", frame_id),
        ("roi_count", roi_count),
        ("input_width", width),
        ("input_height", height),
        ("channels", channels),
    ):
        _nonnegative(value, field, row)

    legacy_roi_samples = _number(row, "roi_pixels")
    roi_spatial_pixels = _number(row, "roi_spatial_pixels")
    roi_bytes = _number(row, "roi_bytes")
    if roi_bytes is None and legacy_roi_samples is not None:
        # The legacy adapter counted uint8 channel samples (area * channels).
        roi_bytes = legacy_roi_samples
    if (
        roi_spatial_pixels is None
        and legacy_roi_samples is not None
        and channels is not None
        and channels > 0
    ):
        roi_spatial_pixels = legacy_roi_samples / channels
    _nonnegative(roi_spatial_pixels, "roi_spatial_pixels", row)
    _nonnegative(roi_bytes, "roi_bytes", row)

    preview_jpeg_bytes = _number(row, "preview_jpeg_bytes", "output_jpeg_bytes")
    packet_count = _integer(row, "packet_count")
    packet_bytes = _number(row, "packet_bytes")
    for field, value in (
        ("preview_jpeg_bytes", preview_jpeg_bytes),
        ("packet_count", packet_count),
        ("packet_bytes", packet_bytes),
    ):
        _nonnegative(value, field, row)

    timestamp_monotonic_s = _number(
        row,
        "timestamp_monotonic_s",
        "captured_monotonic_s",
        "monotonic_s",
    )
    _nonnegative(timestamp_monotonic_s, "timestamp_monotonic_s", row)

    source_csv = _first(row, "source_csv") or "<memory>"
    run_id = _first(row, "run_id") or Path(source_csv).stem
    scene = _first(row, "scene") or "unspecified"
    normalised: dict[str, float | int | str | None] = {
        "run_id": run_id,
        "condition": condition,
        "resolution": _resolution(row, width, height),
        "scene": scene,
        "frame_id": frame_id,
        "roi_count": roi_count,
        "roi_spatial_pixels": roi_spatial_pixels,
        "roi_bytes": roi_bytes,
        "preview_jpeg_bytes": preview_jpeg_bytes,
        "packet_count": packet_count,
        "packet_bytes": packet_bytes,
        "timestamp_utc": _first(row, "timestamp_utc"),
        "timestamp_monotonic_s": timestamp_monotonic_s,
        "source_csv": source_csv,
        "source_order": _integer(row, "source_order") or 0,
        "legacy_schema": int("roi_spatial_pixels" not in row),
        "source_dropped_callbacks": _integer(
            row, "source_dropped_callbacks", "dropped_callbacks"
        ),
        "source_frame_id_available": _integer(row, "source_frame_id_available"),
        "telemetry_enqueued": _integer(row, "telemetry_enqueued"),
        "inline_integrity_audit_enabled": _integer(
            row, "inline_integrity_audit_enabled"
        ),
        "exact_recovery_checks": _integer(row, "exact_recovery_checks"),
        "exact_recovery_passes": _integer(row, "exact_recovery_passes"),
        "tamper_checks": _integer(row, "tamper_checks"),
        "tamper_rejections": _integer(row, "tamper_rejections"),
    }
    for canonical, aliases in TIMING_ALIASES.items():
        value = _number(row, *aliases)
        _nonnegative(value, canonical, row)
        normalised[canonical] = value
    for canonical, aliases in RESOURCE_ALIASES.items():
        value = _number(row, *aliases)
        # The adapter uses -1 only as an explicit unavailable sentinel.
        if value is not None and value < 0:
            value = None
        normalised[canonical] = value
    return normalised


def _values(
    items: list[dict[str, float | int | str | None]], field: str
) -> list[float]:
    return [float(item[field]) for item in items if item.get(field) is not None]


def _median(items: list[dict[str, float | int | str | None]], field: str) -> float | None:
    values = _values(items, field)
    return float(np.median(values)) if values else None


def _p95(items: list[dict[str, float | int | str | None]], field: str) -> float | None:
    values = _values(items, field)
    return float(np.percentile(values, 95)) if values else None


def _timestamp_rate(
    items: list[dict[str, float | int | str | None]],
    predicate: Callable[[dict[str, float | int | str | None]], bool],
    *,
    byte_field: str | None = None,
) -> tuple[float | None, float | None, int, str]:
    events = [
        item
        for item in sorted(items, key=lambda item: int(item["source_order"] or 0))
        if item.get("timestamp_monotonic_s") is not None and predicate(item)
    ]
    if len(events) < 2:
        return None, None, len(events), "unavailable_fewer_than_two_timestamped_outputs"

    timestamps = [float(item["timestamp_monotonic_s"]) for item in events]
    intervals = np.diff(np.asarray(timestamps, dtype=float))
    if not np.all(intervals > 0.0):
        return None, None, len(events), "unavailable_non_increasing_timestamps"
    elapsed = float(intervals.sum())
    fps = float((len(events) - 1) / elapsed)

    throughput = None
    if byte_field is not None and all(item.get(byte_field) is not None for item in events):
        # Each interval is charged with the output observed at its right edge.
        transferred = sum(float(item[byte_field]) for item in events[1:])
        throughput = float(transferred / elapsed)
    return fps, throughput, len(events), "ok"


def summarize(
    rows: list[dict[str, str]],
) -> list[dict[str, float | int | str | None]]:
    normalised = [_normalise_row(row) for row in rows]
    grouped: dict[
        tuple[str, str, str, str],
        list[dict[str, float | int | str | None]],
    ] = defaultdict(list)
    for row in normalised:
        key = (
            str(row["run_id"]),
            str(row["condition"]),
            str(row["resolution"]),
            str(row["scene"]),
        )
        grouped[key].append(row)

    summary: list[dict[str, float | int | str | None]] = []
    for (run_id, condition, resolution, scene), items in sorted(grouped.items()):
        preview_fps, preview_throughput, preview_events, preview_rate_status = (
            _timestamp_rate(
                items,
                lambda item: float(item.get("preview_jpeg_bytes") or 0.0) > 0.0,
                byte_field="preview_jpeg_bytes",
            )
        )
        protected_fps, protected_throughput, protected_events, protected_rate_status = (
            _timestamp_rate(
                items,
                lambda item: str(item.get("condition")) in {"M3_aead", "M4_lorenz_aead"}
                and int(item.get("packet_count") or 0) > 0,
                byte_field="packet_bytes",
            )
        )
        record: dict[str, float | int | str | None] = {
            "run_id": run_id,
            "condition": condition,
            "resolution": resolution,
            "scene": scene,
            "frames": len(items),
            "source_csv_files": len({str(item["source_csv"]) for item in items}),
            "legacy_rows": sum(int(item["legacy_schema"] or 0) for item in items),
            "frames_with_roi": sum(int(item["roi_count"] or 0) > 0 for item in items),
            "median_roi_spatial_pixels": _median(items, "roi_spatial_pixels"),
            "median_roi_bytes": _median(items, "roi_bytes"),
            "median_preview_jpeg_bytes": _median(items, "preview_jpeg_bytes"),
            "median_packet_count": _median(items, "packet_count"),
            "median_packet_bytes": _median(items, "packet_bytes"),
            "timestamped_preview_outputs": preview_events,
            "preview_output_fps": preview_fps,
            "preview_throughput_bytes_s": preview_throughput,
            "preview_rate_status": preview_rate_status,
            "timestamped_protected_outputs": protected_events,
            "protected_output_fps": protected_fps,
            "protected_payload_throughput_bytes_s": protected_throughput,
            "protected_rate_status": protected_rate_status,
        }
        for field in TIMING_ALIASES:
            record[f"n_{field}"] = len(_values(items, field))
            record[f"median_{field}"] = _median(items, field)
            record[f"p95_{field}"] = _p95(items, field)
        for field in RESOURCE_ALIASES:
            record[f"n_{field}"] = len(_values(items, field))
            record[f"median_{field}"] = _median(items, field)
            record[f"p95_{field}"] = _p95(items, field)

        telemetry = _values(items, "telemetry_enqueued")
        record["telemetry_enqueued_fraction"] = (
            float(np.mean(telemetry)) if telemetry else None
        )
        source_id_available = _values(items, "source_frame_id_available")
        record["source_frame_id_available_fraction"] = (
            float(np.mean(source_id_available)) if source_id_available else None
        )
        inline_audit = _values(items, "inline_integrity_audit_enabled")
        record["inline_integrity_audit_enabled_fraction"] = (
            float(np.mean(inline_audit)) if inline_audit else None
        )
        for field in (
            "exact_recovery_checks",
            "exact_recovery_passes",
            "tamper_checks",
            "tamper_rejections",
        ):
            values = _values(items, field)
            record[f"total_{field}"] = int(sum(values)) if values else None
        summary.append(record)
    return summary


def write_outputs(
    summary: list[dict[str, float | int | str | None]],
    output_dir: Path,
    figure_dir: Path,
) -> None:
    if not summary:
        raise ValueError("cannot write an empty board summary")
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "unoq_board_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "unoq_board_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    labels = [
        f"{record['run_id']}\n{record['condition']}\n{record['resolution']} / {record['scene']}"
        for record in summary
    ]
    available_stages = [
        stage
        for stage in TIMING_ALIASES
        if any(record[f"median_{stage}"] is not None for record in summary)
    ]
    x = np.arange(len(labels))
    fig_width = min(18.0, max(10.5, 1.4 * len(labels)))
    fig, ax = plt.subplots(figsize=(fig_width, 5.2))
    if available_stages:
        colors = ("#4c78a8", "#f58518", "#e45756", "#54a24b", "#b279a2")
        width = 0.82 / len(available_stages)
        centre = (len(available_stages) - 1) / 2.0
        for index, stage in enumerate(available_stages):
            values = [
                np.nan if record[f"median_{stage}"] is None else record[f"median_{stage}"]
                for record in summary
            ]
            ax.bar(
                x + (index - centre) * width,
                values,
                width,
                label=stage,
                color=colors[index % len(colors)],
            )
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No timing fields available", ha="center", va="center")
    ax.set_xticks(x, labels, rotation=18, ha="right")
    ax.set_ylabel("Median stage time (ms)")
    ax.set_title("Physical Arduino UNO Q measurements")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(figure_dir / "unoq_board_latency.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path, help="UNO Q metrics CSV files")
    parser.add_argument("--output-dir", type=Path, default=Path("data/board"))
    parser.add_argument("--figure-dir", type=Path, default=Path("../figures"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(expand_inputs(args.inputs))
    result = summarize(rows)
    write_outputs(result, args.output_dir, args.figure_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

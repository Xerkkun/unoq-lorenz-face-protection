# Physical-board data only

Place raw CSV files copied from Arduino UNO Q under `raw/`, one file per run.
Do not place development-host verification data here.

Use a filename that preserves the run and condition, for example:

```text
raw/20260725_run01_M4_lorenz_aead_640x480.csv
```

Keep the matching run manifest next to each CSV. The master key, participant
names, raw face images, and consent forms do not belong in this directory.

From the `software/` directory, summarize board data with:

```powershell
python scripts/summarize_board_metrics.py data/board/raw/*.csv
```

Generated summaries remain distinct from `data/software_verification_*`, whose
timings describe the Windows development host.

## Current CSV schema

Each raw row must identify `run_id`, `condition`, `scene`, `input_width`, and
`input_height`. Use the names below without changing their units:

| Field | Unit or meaning |
| --- | --- |
| `timestamp_utc` | ISO-8601 wall-clock audit stamp |
| `timestamp_monotonic_s` | monotonic seconds used only for within-run rates |
| `roi_spatial_pixels` | sum of ROI width times height; channels are not included |
| `roi_bytes` | uncompressed ROI bytes across all channels |
| `preview_jpeg_bytes` | lossy browser-preview JPEG; not a recoverable packet |
| `packet_count`, `packet_bytes` | persisted authenticated ROI packets and their serialized bytes |
| `decode_ms`, `protect_ms`, `packet_store_ms` | Linux application stage times |
| `integrity_audit_ms` | optional in-memory recovery/tamper audit time |
| `inline_integrity_audit_enabled` | `1` only for a dedicated integrity run |
| `exact_recovery_checks`, `exact_recovery_passes` | direct in-memory source comparisons |
| `tamper_checks`, `tamper_rejections` | modified ciphertext copies tested/rejected |
| `preview_encode_ms`, `callback_core_ms` | Linux preview/core callback times |
| `process_cpu_percent` | Linux process CPU estimate between completed callbacks |
| `process_rss_kib` | resident set size of the Linux process, or `-1` when unavailable |
| `system_memory_percent` | whole-system Linux memory use, or blank/NaN when unavailable |
| `source_dropped_callbacks` | source-level drops, or `-1` when unavailable |
| `source_frame_id_available` | `1` only when the source exposes a shared frame identifier |
| `telemetry_enqueued` | whether the optional MCU status message entered its queue |

The summarizer groups only rows with the same
`run_id + condition + resolution + scene`. `preview_output_fps` is a preview
rate; `protected_output_fps` requires timestamped rows with at least one
authenticated packet. Rates remain blank when fewer than two qualifying
monotonic timestamps exist or when timestamps do not increase. Throughput is
reported in bytes per second and never inferred from latency alone.

Legacy CSV files remain readable. Their `output_jpeg_bytes`, `encode_ms`, and
`callback_total_ms` columns map to the corresponding preview/core fields. The
old `roi_pixels` value counted uint8 channel samples, so it maps to
`roi_bytes`; spatial area stays blank unless a channel count is also present.

## Box--frame alignment protocol

The inspected detection Brick does not expose a source-frame identifier shared
by the classification and callback JPEG. Therefore the callback-local
`frame_id` cannot establish alignment, detector recall, or source-frame drops.
Before publication, use either an instrumented Brick with a shared sequence
number or a separate synchronized capture with visible time/frame markers.
Audit a preregistered sample of callbacks and record the observed box offset.

Exact source equality also cannot be reconstructed after capture when no raw
ROI was retained. Use `inline_integrity_audit=true` in a dedicated validation
run; keep it disabled in performance runs and report its timing separately.

Preregister a symmetric bounding-box margin per run. Record both the requested
and actually applied fractions in the manifest; do not claim a margin was used
unless the adapter revision records it in every metrics row. The same value
must be used for every condition in a comparison, with clipping at image
boundaries documented.

## MCU telemetry boundary

The STM32U585 sketch buffers status values forwarded by Linux and prints a JSON
status line over serial once per second. `last_linux_reported_protect_us` is
not an MCU latency measurement. The buffer/counters show delivery and mode
state only; UNO Q timing comes from the Linux CSV unless a separate,
calibrated MCU timing experiment is implemented.

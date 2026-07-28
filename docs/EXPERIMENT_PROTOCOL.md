# Physical Arduino UNO Q experiment protocol

This protocol is the shortest defensible path from the executable host
baseline to results that may be reported as Arduino UNO Q measurements.

## Freeze before collecting data

Record the UNO Q board revision and RAM variant, power supply, smartphone model,
mobile OS and Arduino IoT Remote versions, selected front/rear camera,
orientation, decoded resolution and exposure policy, Arduino App Lab version,
installed Brick versions, face-model identifier/hash, Git revision or ZIP
SHA-256, confidence threshold, run identifier, condition, and whether the
device was rebooted. Record whether the phone and board used different Wi-Fi
bands, together with Python, NumPy, packet-protocol and authenticated transform
profile versions. Generate a fresh 32-byte master key for each run and never
copy it to the paper data directory; only its fingerprint belongs in the
private run contract. The temporary Arduino IoT Remote pairing code is not the
ROI master key.

## Conditions

1. `M0_detection`: decode and detection callback only.
2. `M1_blur`: irreversible ROI blur/pixelation preview.
3. `M2_lorenz_only`: reversible Lorenz preview, laboratory ablation only.
4. `M3_aead`: AEAD of the original ROI.
5. `M4_lorenz_aead`: Lorenz transform followed by AEAD.

Target 640x480 and 1280x720 and record the actual decoded width and height for
every callback; do not relabel a phone stream whose negotiated resolution
differs. For each available resolution and condition, collect five 60-second
runs after warm-up under stationary-face, head-motion, and controlled
illumination-change scenes. Keep the phone mount, selected lens, orientation
and exposure policy fixed across conditions.

## Required measurements

- protected packet-output FPS and operational-preview FPS from monotonic
  timestamps; report source drops only if separately instrumented;
- decode, combined ROI protection, atomic packet-store, preview-encode, and
  callback-core latency. Compare M3 against M4 for incremental Lorenz cost;
- median, interquartile range, and p95 for each stage;
- QRB2210 process CPU, resident memory, temperature if available, and power if measured
  with an identified instrument;
- ROI spatial pixels, ROI bytes, preview JPEG bytes, serialized packet bytes,
  and authenticated packet count as separate units;
- detector precision, recall, missed-face rate, and IoU on at least 300
  distributed annotations;
- exact authorized ROI recovery and maximum absolute pixel error;
- rejection after changing ciphertext, tag, AAD, nonce, and key;
- replay rejection under the receiving counter policy.

Use two explicit run types. Integrity-validation runs set
`inline_integrity_audit=true`; the callback compares each recovered ROI with
the source ROI in memory, tests a modified ciphertext copy, records counts and
`integrity_audit_ms`, and retains no source pixels. Performance runs set the
option to `false` so the audit does not perturb the M3--M4 timing comparison.
Do not infer exact source recovery retrospectively from decryptable packets
when the original ROI was not retained or compared.

If a real paper illustration is explicitly authorized, enable
`publication_frame_enabled` only in a unique M3/M4 run. Release the single
protected operational preview, never the decoded source frame, and record its
SHA-256, run identifier, protection condition, and consent basis.

Do not call callback-to-preview time inference latency. Do not report host
timings as board data. Image entropy, histogram, adjacent correlation, NPCR,
and UACI may be reported as visual diagnostics only.

Summaries must remain separated by `run_id + condition + resolution + scene`.
Never aggregate runs first and then compute a single percentile or frame rate.

The inspected official `VideoObjectDetection` source invokes `on_detect_all`
only when at least one bounding box survives filtering. Consequently, the
current adapter cannot count negative or missed frames by itself. Detector
recall and missed-face rate require a separately synchronized annotated source
or an explicitly instrumented Brick that reports empty detections. Do not infer
zero misses from the callback CSV.

## Stop conditions

Stop and fix the pipeline if a raw stream is reachable from the experiment UI,
a detector miss silently displays an unprotected face in a claimed protected
mode, a nonce repeats under one key, a modified packet renders, the key enters
a log, or raw participant video is written without the approved consent and
retention procedure.

## Minimum manuscript update after the run

Replace the board-results placeholders/status text with the registered sample
count and summary table; add the raw CSV hash; identify exclusions; state every
software/hardware version; and keep host verification in a separate table.

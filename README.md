# UNO Q Lorenz facial-region protection prototype

This package is the implementation companion for the EDIESCA 2026 manuscript.
It is intentionally split into two layers:

1. `python/unoq_lorenz/` contains the platform-independent, testable core:
   Lorenz integration, a reversible permutation--diffusion transform, nonce
   management, ChaCha20-Poly1305 protection, ROI packetization, and metrics.
2. `python/main.py`, `app.yaml`, and `sketch/` provide the Arduino App Lab and
   STM32U585 integration points for UNO Q.

The Lorenz transform is an experimental preprocessing layer. It is **not** a
cryptographic primitive and is never credited with confidentiality or
integrity. Those properties come from ChaCha20-Poly1305. The transform and the
AEAD key are domain-separated from one 32-byte master key with HKDF-SHA-256.

For a complete classroom workflow, data-retention alternatives, deployment,
troubleshooting, statistical-stream exercises, and reproducibility checklists,
read `docs/MANUAL_REPRODUCCION_ESTUDIANTES.md` or
`docs/STUDENT_REPRODUCTION_MANUAL.md`. The public companion repository is
intended to be:
`https://github.com/Xerkkun/unoq-lorenz-face-protection`.

## Local verification

Create an environment with the dependencies declared in `pyproject.toml`, then
run:

```powershell
python -m pytest -q
python scripts/run_verification.py
python scripts/generate_figures.py
```

The generated timing data are development-host diagnostics only. They are not
UNO Q measurements and must not be reported as such.

After copying physical-board CSV files into a board-only directory, summarize
them separately with:

```powershell
python scripts/summarize_board_metrics.py data/board/raw/*.csv
```

The summarizer groups data by run, condition, resolution, and scene, and
generates `unoq_board_summary.csv`, `unoq_board_summary.json`, and a PNG latency
figure. It accepts the older board schema conservatively but never relabels its
channel-sample count as spatial area. Never pass
`software_verification_cases.csv` to that command.

## UNO Q deployment path

1. In Arduino App Lab, duplicate the official **Detect Objects on Smartphone
   Camera** example. The adapter combines its `WebSocketCamera` input with the
   official face-detection model.
2. Replace its `app.yaml` and `python/main.py` with the files in this package;
   copy `python/unoq_lorenz/`, `assets/`, and `sketch/` as well.
3. Put the UNO Q and the smartphone on the same isolated laboratory LAN. Pair
   Arduino IoT Remote with the QR code shown by the protected WebUI. A 2.4 GHz
   phone and a 5 GHz UNO Q are acceptable only when the router bridges both
   bands without client isolation.
4. Assign a unique run and scene before launching, either through process
   variables:

   ```text
   UNOQ_RUN_ID=20260725_run01
   UNOQ_SCENE=stationary
   UNOQ_CONDITION=M4_lorenz_aead
   UNOQ_BBOX_MARGIN_FRACTION=0.10
   ```

   or through `/app/data/private/run_config.json`:

   ```json
   {
      "run_id": "20260725_run01",
      "scene": "stationary",
      "condition": "M4_lorenz_aead",
      "bbox_margin_fraction": 0.10,
      "inline_integrity_audit": false,
      "publication_frame_enabled": false
   }
   ```

   Process variables take precedence. The run-config file contains no key and
   stays outside release artifacts.

   With no supplied key, the adapter creates a fresh 32-byte key in the private
   `UNOQ_SECRET_DIR` (default `/app/data/private`) using an exclusive file. You
   may instead provide exactly one of `UNOQ_MASTER_KEY_B64` or
   `UNOQ_MASTER_KEY_FILE`. Never copy that file into the release dataset. The
   packet store records only its SHA-256 fingerprint and refuses a fingerprint
   already used by another retained run. Record the requested/applied margin
   and the key origin, never the key, in the run manifest.

5. Start with synthetic or consented video. For a dedicated physical integrity
   run, set `inline_integrity_audit` to `true`. Each accepted ROI is then
   decrypted and compared byte-for-byte with the source ROI in memory, and one
   modified ciphertext copy must be rejected. No source pixels or comparison
   hashes are retained. Keep this audit disabled in performance runs and report
   its separate `integrity_audit_ms` cost when enabled.

   For an explicitly authorized paper illustration, set
   `publication_frame_enabled` to `true` in a unique authenticated run. The
   adapter writes exactly one M3/M4 operational preview under
   `/app/data/board/publication/`; the decoded source frame is never written.
   When time is needed to compose the scene, set
   `publication_frame_arm_file` to a file under `/app/data/private`. The app
   keeps processing without saving the publication preview until that file
   exists, then captures exactly one protected preview and removes the arm
   file. This permits an explicit operator-ready signal without restarting or
   reconnecting the smartphone.
   Treat the protected preview as participant-derived material and release it
   only under the applicable consent and ethics procedure.

Select one registered condition with `UNOQ_CONDITION`:

```text
M0_detection
M1_blur
M2_lorenz_only
M3_aead
M4_lorenz_aead
```

The default is `M4_lorenz_aead`. Conditions M0--M2 are intentionally blocked
unless `UNOQ_ALLOW_INSECURE_ABLATION=1` is also set. That opt-in is for a
controlled experiment only; it prevents a misspelled or forgotten condition
from silently disabling authenticated protection.

The App Lab base image already includes NumPy, OpenCV, and `cryptography` in
the current official Arduino Bricks source. Recheck this when App Lab is
updated. The adapter passes an encrypted `WebSocketCamera` to
`VideoObjectDetection(camera_preview=True)` so its callback receives JPEG
bytes and bounding boxes from the official face model. The phone-pairing
ChaCha20-Poly1305 transport is a separate channel and is not counted as the
paper's ROI protection. Browser helpers under `assets/libs/` are preserved
from official Arduino examples; their provenance and licenses are recorded in
`THIRD_PARTY_NOTICES.md`.

The preview route never embeds the Brick's raw `/embed` stream. The browser
receives only a lossy operational JPEG, never the recoverable ROI packet. Its
red warning remains visible for M0--M2, and the packet store must be verified
separately for M3--M4. If a face is missed by the detector, its pixels cannot
be protected; this limitation must be measured and reported rather than hidden
behind the cryptographic layer.

Network Mode must run on an isolated, trusted laboratory network with public
port forwarding and tunnels disabled. Keep generated/provisioned run keys in
the private data area; never place one in `app.yaml`, the WebUI, a URL, source
control, logs, CSV files, or a run manifest. The six-digit phone-pairing code
is temporary transport metadata, not a master key. Automatic private-file
generation and the non-secret run-config file avoid making App Lab environment
injection a prerequisite.

In M3/M4, a canonical JSON frame bundle is written atomically under
`UNOQ_PACKET_DIR/<run_id>/` before metrics or preview success is emitted. The
lossy JPEG is never the recovery artifact. A store/logging failure triggers the
WebUI `pipeline_error` path and removes the stale preview.

## Real-time data destinations

The default sink is local atomic storage on the UNO Q. A deployment must choose
and document one of four policies:

- ephemeral processing: protected live preview and aggregate metrics only;
- authenticated packet delivery to a trusted laboratory computer;
- mutually authenticated transport to a remote/cloud queue or object store;
- event-triggered retention from a bounded in-memory ring.

Only authenticated M3/M4 packets should be used when authorized exact recovery
is required. A receiver must acknowledge atomic storage before board deletion
and deduplicate retries by packet identity and digest. Remote services require
least-privilege credentials, separate key custody, audit logging, and lifecycle
deletion. Event capture requires a declared trigger, pre/post window, quota,
false-trigger policy, and retention deadline. During disconnection, select
bounded buffering, back-pressure, or explicit dropping; never let an
unbounded queue consume eMMC. Detailed procedures appear in the two student
manuals.

The optional inline integrity audit adds
`exact_recovery_checks`, `exact_recovery_passes`, `tamper_checks`,
`tamper_rejections`, and `integrity_audit_ms` to each physical-run row. An
exact-recovery claim requires this direct in-memory comparison; decrypting a
previously stored packet without the original ROI is only a decryptability and
shape check.

In the official source snapshot inspected on 2026-07-20, `on_detect_all` is
invoked only when a classification message contains at least one accepted
bounding box. Thus this adapter's CSV covers positive callbacks; it cannot by
itself establish detector recall or zero dropped/missed frames. Use a separate
synchronized annotation stream or instrument the Brick before making those
claims.

The classification and callback JPEG also lack a shared source-frame ID, so a
callback-local counter does not prove box--frame alignment. Preregister and
record a fixed symmetric bounding-box margin, clip it at image boundaries, and
audit alignment with an instrumented Brick or synchronized visible frame/time
markers before comparing conditions.

The STM32U585 sketch buffers the last 32 forwarded status messages, counts
authenticated and unauthenticated mode messages, drives the LED from the
forwarded `authenticatedMode` flag, and prints one JSON status line per second.
Its `last_linux_reported_protect_us` field is forwarded telemetry, not a timing
measurement made by the MCU.

## Evidence boundary

- Unit tests and host verification: executable now.
- App Lab API compatibility: based on the official Arduino source snapshot
  inspected on 2026-07-20.
- Transform compatibility: the authenticated profile binds the exact NumPy
  runtime version and `Generator(PCG64).permutation+integers` API. Freeze the
  physical-board version in the run manifest and recovery environment.
- Physical UNO Q integration: one 2026-07-28 smartphone-camera M4 pilot is
  recorded under `data/board/raw/`. It provides preliminary positive-callback
  timing, CPU/RAM, packet persistence, board-local authentication, tamper, and
  replay evidence only.
- Full UNO Q comparison, detector recall/alignment, temperature, power, and
  sustained multi-run behavior: pending the registered campaign.
- Security claim: limited to the selected AEAD construction and nonce/key
  contract; visual statistics do not prove security.

## Experiment contract before submission

- Use a new 32-byte master key and a new process for each run.
- Keep the original camera video in memory only; do not write it to disk.
- Use synthetic images or adults who gave explicit consent.
- Run the five declared conditions (detection-only, blur, AEAD, Lorenz-only
  ablation, and Lorenz+AEAD) at each selected resolution.
- Report median and 95th-percentile stage latency, preview FPS, authenticated
  packet-output FPS, byte throughput, exact recovery, tag rejection, and
  missed-face rate. Report source drops only when a source-frame ID makes them
  observable; otherwise retain `-1`/unavailable.
- Keep `roi_spatial_pixels`, `roi_bytes`, `preview_jpeg_bytes`, and
  `packet_bytes` as separate quantities with their stated units.
- Never relabel host timing as QRB2210 or STM32U585 performance.

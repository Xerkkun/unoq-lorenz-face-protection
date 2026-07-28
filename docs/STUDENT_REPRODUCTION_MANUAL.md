# Engineering student reproduction manual

## 1. Purpose and scope

This manual accompanies the paper on authenticated facial-region protection
on Arduino UNO Q. It is intended to let an engineering team:

1. verify the implementation without a camera by using synthetic images;
2. understand the exact permutation, mask, and authenticated-packet protocol;
3. deploy the application on an UNO Q with a smartphone camera;
4. decide which real-time data to discard, retain, or transmit;
5. measure implementation cost without relabeling host results as board
   results; and
6. report privacy, detector, and security limitations.

The prototype is an educational and experimental platform, not a certified
biometric product. The Lorenz-derived transform is not presented as a cipher.
M3/M4 packet confidentiality and integrity come from ChaCha20-Poly1305, with
HKDF-SHA-256 key separation.

## 2. Learning outcomes

After the exercise, a student should be able to explain:

- visual obfuscation versus encryption, authentication, and detection;
- why a face missed by the detector cannot be protected downstream;
- why a nonce must not repeat under one key;
- which metadata are bound as associated data;
- how an M3/M4 packet recovers an ROI exactly;
- what statistical bit tests can and cannot establish;
- why work is divided between the Linux QRB2210 and STM32U585;
- how to select a retention policy for a real-time application.

## 3. Evidence and claim boundaries

| Evidence | Supported claim | Unsupported claim |
|---|---|---|
| PC unit tests | Code invariants in that environment | UNO Q performance |
| Synthetic cases | Recovery, tamper rejection, serialization | Real-face accuracy |
| UNO Q M4 pilot | Smartphone integration and preliminary timing | M0--M4 comparison |
| In-memory audit | Byte-exact current-ROI recovery | Security against all attacks |
| NIST/TestU01/etc. | Detectable statistical defects | Cryptographic security |
| Protected frame | Implemented display boundary | Detector recall or key secrecy |

Never relabel Windows timing as QRB2210 or STM32U585 timing. A noisy-looking
image is not evidence of confidentiality.

## 4. Reference platform

### 4.1 Manufacturer specification

Arduino UNO Q combines:

- a Qualcomm Dragonwing QRB2210 application processor with four Arm Cortex-A53
  cores at up to 2.0 GHz;
- an Adreno GPU and two image signal processors;
- an STM32U585 Arm Cortex-M33 MCU at up to 160 MHz, with 2 MB flash and 786 kB
  SRAM;
- Debian Linux on the QRB2210 and Zephyr-based sketches on the STM32U585;
- Wi-Fi 5 at 2.4/5 GHz, Bluetooth 5.1, and Bridge/RPC communication;
- official 2/4 GB LPDDR4X and 16/32 GB eMMC variants.

### 4.2 Pilot-observed configuration

These values belong to the board and run observed on 2026-07-28:

| Item | Observed value |
|---|---|
| Reported model | Arduino UnoQ |
| RAM | 4 GB variant; 3,755,164 kB reported usable |
| Architecture | `aarch64`, four Kryo-V2 CPUs, maximum 2016 MHz |
| Distribution | Debian GNU/Linux 13.5 (trixie) |
| Kernel | `7.0.0-g122c2c22d838` |
| App CLI/daemon | 0.12.1 / 0.12.1 |
| `arduino_app_bricks` | 0.11.0 |
| Application Python | 3.13.14 |
| NumPy | 2.4.6 |
| Cryptography | 49.0.0 |
| OpenCV | 4.13.0 |
| Real input | smartphone, decoded 480x640 portrait JPEG |
| Observed network | phone 2.4 GHz, UNO Q 5 GHz, bridged LAN |

Record these values again for every campaign. The authenticated transform
profile binds the NumPy version because an API change can alter the reproduced
permutation.

## 5. Required material

For host-only verification:

- a computer with Python 3.11 or later;
- Git;
- approximately 1 GB of free space;
- this repository.

For board integration:

- Arduino UNO Q and suitable USB-C power;
- a computer running Arduino App Lab;
- an Android or iOS phone running Arduino IoT Remote;
- a LAN that permits client-to-client communication;
- explicit consent from every participant;
- optionally, identified power and temperature instruments.

A 2.4 GHz phone and a 5 GHz board can communicate when the router bridges both
bands. Disable guest-network and access-point client isolation.

## 6. Repository map

```text
app.yaml                         App Lab definition
python/main.py                   camera, detector, and WebUI adapter
python/unoq_lorenz/              platform-independent core
sketch/                          STM32U585 sketch
assets/                          local interface and Arduino assets
tests/                           unit tests
scripts/run_verification.py      reproducible synthetic campaign
scripts/generate_figures.py      non-biometric figures
scripts/summarize_board_metrics.py board CSV summarizer
scripts/export_schedule_bitstreams.py statistical-test streams
data/                            non-sensitive public evidence
docs/                            theory, protocol, ethics, and manuals
```

Real-run packets, keys, raw video, consent records, and participant images are
not public repository artifacts.

## 7. Host setup

### Windows PowerShell

```powershell
git clone https://github.com/Xerkkun/unoq-lorenz-face-protection.git
Set-Location unoq-lorenz-face-protection
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/run_verification.py
```

If activation is blocked:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_verification.py
```

### Linux or macOS

```bash
git clone https://github.com/Xerkkun/unoq-lorenz-face-protection.git
cd unoq-lorenz-face-protection
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/run_verification.py
```

Successful execution produces synthetic evidence under `data/`. Its timing is
host timing, not board timing.

## 8. Exact bit-construction chain

The versioned chain is:

```text
K -> (K_A, K_L) -> Lorenz state -> D_L
  -> HKDF(nonce, length, version, D_L)
  -> PCG64 seed -> permutation + mask
  -> reversible transform -> ChaCha20-Poly1305
```

### Key separation

Each run creates a random 32-byte master key `K`. HKDF-SHA-256 derives:

- `K_A`, the ChaCha20-Poly1305 key;
- `K_L`, the numerical-schedule key.

Never write `K` to source control, `app.yaml`, a URL, WebUI, CSV, or manifest.
A manifest may include only a one-way SHA-256 fingerprint.

### Lorenz numerical profile

`lorenz-rk4-sha256-pcg64-v2` uses:

- `sigma=10`, `rho=28`, and `beta=8/3`;
- binary64 arithmetic;
- fixed-step RK4 with `h=0.005`;
- 2048 discarded states and 512 retained states;
- coordinate multiplication by `10^9`;
- rounding and little-endian signed `int64` serialization;
- SHA-256 to produce `D_L`.

This work occurs once when the protector is constructed.

### Per-packet schedule

For each 96-bit nonce `N` and ROI byte length `n`, HKDF-SHA-256 produces 32
bytes from the version, `n`, and `D_L`. The first 128 bits seed
`Generator(PCG64)`, which emits the permutation and a `uint8` mask.

PCG64 is present for experiment reproducibility, not cryptographic
unpredictability. Packet security relies on ChaCha20-Poly1305.

### Transform, nonce, and replay

For contiguous ROI bytes `P`:

```text
q[i] = p[permutation[i]] XOR mask[i]
p[permutation[i]] = q[i] XOR mask[i]
```

M4 authenticates encrypted `Q`; M3 authenticates encrypted `P`. The receiver
authenticates, checks profile compatibility, and only then returns pixels.

The nonce concatenates a random 64-bit prefix and a locked 32-bit counter.
Counter exhaustion fails closed. Associated data bind run, packet, callback
and ROI identifiers, box, shape, condition, protocol, algorithms, and the
complete transform profile. Replay state is updated only after successful
authentication.

## 9. Statistical stream export

The included script emits deterministic public teaching streams, never a
production-key stream:

```powershell
python scripts/export_schedule_bitstreams.py `
  --output-dir data/bitstreams `
  --streams 10 `
  --bytes-per-stream 1000000
```

Inspect `manifest.json` for byte lengths and SHA-256 values. Before using NIST
SP 800-22, TestU01, PractRand, or Dieharder, preregister stream count, sample
size, significance level, multiple-comparison rule, and pass criterion.
Document exact bit order and endianness.

Passing such suites does not establish key secrecy, unpredictability, chosen
input resistance, or nonce safety. Future profiles may use SHA-3/BLAKE
extraction, ChaCha20 or AES-CTR DRBG, independent entropy sources, or coupled
nonlinear maps, but each requires a new identifier and fresh compatibility,
functional, and security analysis.

## 10. Arduino UNO Q deployment

1. Open Arduino App Lab.
2. Duplicate **Detect Objects on Smartphone Camera**.
3. Replace `app.yaml` and `python/main.py`.
4. Copy `python/unoq_lorenz/`, `assets/`, and `sketch/`.
5. Confirm the `face-detection` model.
6. Put phone and board on one trusted LAN.
7. Start the application.
8. Scan the six-digit pairing code with Arduino IoT Remote.
9. Wait for positive callbacks in the protected WebUI.

The pairing code secures the camera transport; it is not the ROI master key.

## 11. Run contract and conditions

Create `/app/data/private/run_config.json` outside the repository:

```json
{
  "run_id": "20260728_student01",
  "scene": "stationary",
  "condition": "M4_lorenz_aead",
  "bbox_margin_fraction": 0.10,
  "inline_integrity_audit": false,
  "publication_frame_enabled": false
}
```

Environment variables are also accepted and take precedence:

```text
UNOQ_RUN_ID=20260728_student01
UNOQ_SCENE=stationary
UNOQ_CONDITION=M4_lorenz_aead
UNOQ_BBOX_MARGIN_FRACTION=0.10
```

Use a fresh run identifier and key after each restart.

| ID | Operation | Purpose |
|---|---|---|
| M0 | detection without ROI modification | insecure baseline |
| M1 | Gaussian blur | visual-only obfuscation |
| M2 | Lorenz transform only | unauthenticated ablation |
| M3 | original ROI under AEAD | standard cryptographic baseline |
| M4 | Lorenz transform plus AEAD | proposed composition |

M0--M2 require `UNOQ_ALLOW_INSECURE_ABLATION=1` and belong only in a controlled
experiment on an isolated network.

## 12. Real-time data-handling policies

Select and record one policy before a run. Do not change policies inside one
experimental comparison.

### A. Ephemeral processing

```text
phone -> detection -> M3/M4 -> protected preview -> discard
```

Retain only aggregate counters without personal identifiers. Use bounded
buffers and release array references after the callback. This minimizes data
but provides no recoverable audit history.

### B. Local computer receiver

```text
UNO Q -> authenticated packet -> TLS/trusted LAN -> lab receiver -> disk
```

Authenticate the receiver, accept only M3/M4, publish files atomically,
acknowledge receipt before board deletion, and use `packet_id` plus a digest
for idempotent retries. Restrict firewall and directory permissions, separate
key custody from packet storage, and set a deletion date.

During disconnection, use a predefined bounded buffer, back-pressure, or
explicit dropping. An unlimited queue can exhaust eMMC.

### C. Remote service or cloud

```text
UNO Q -> mutual TLS/VPN -> queue or object store -> authorized processing
```

Use least-privilege credentials, rotation, server audit, encryption at rest,
and lifecycle deletion. Do not store the recovery key in the same object or
account as packets. Record storage region, controller, purpose, retention
period, and deletion procedure.

Transport encryption protects a different boundary and does not replace
packet AEAD. A cloud service may still observe timing, size, and frequency.

### D. Event-triggered retention

```text
bounded RAM ring -> declared event -> pre/post window -> M3/M4 packets
```

Define the trigger: operator button, digital input, zone crossing, state
change, or another measurable signal. Specify:

- pre-event and post-event duration;
- protected-packet-only buffering;
- simultaneous-event priority;
- hourly/daily quota;
- deduplication;
- trigger false positives and false negatives;
- authorized recovery role;
- deletion deadline.

Do not use the lossy operational JPEG when exact recovery is required. The
publication-frame feature stores exactly one operator-armed protected preview
and never the source frame.

### Minimum metadata

Retain only the required run/packet identifier, event time, condition,
protocol version, necessary ROI shape/box, nonce, ciphertext/tag, associated
data, software/profile hashes, and delivery/retention status. Remove phone,
SSID, location, account, participant, serial-number, and private-address
identifiers from public artifacts.

## 13. Integrity audit and operator-armed capture

For a dedicated integrity run:

```json
{
  "inline_integrity_audit": true,
  "publication_frame_enabled": false
}
```

Every current ROI is recovered and compared byte-for-byte in memory. A
modified ciphertext copy must fail. Do not merge these timings with a
performance run.

To allow camera-composition time:

```json
{
  "inline_integrity_audit": true,
  "publication_frame_enabled": true,
  "publication_frame_arm_file": "/app/data/private/capture.ready"
}
```

Streaming continues without saving a figure. Create `capture.ready` only after
the participant signals readiness. The application consumes the file and
retains one protected preview.

## 14. Recommended board campaign

1. Warm up the system.
2. Test M0--M4.
3. Use 640x480 and 1280x720 only when actually delivered by the source.
4. Include stationary face, head motion, and controlled illumination change.
5. Run five 60-second repetitions per cell.
6. Use a new key, process, and `run_id` for each run.
7. Keep inline audit separate from performance.
8. Annotate at least 300 distributed frames for face presence and overlap.
9. Report power/temperature only from an identified instrument.
10. Preserve raw rows and grouped summaries.

The inspected official callback exposes positive detections only and the box
does not share a source identifier with its JPEG. Detector recall, source
drops, and box--frame alignment require synchronized input or further
instrumentation.

## 15. Metrics and units

Keep `roi_spatial_pixels`, `roi_bytes`, `preview_jpeg_bytes`, `packet_bytes`,
and `packet_count` separate. Report median and 95th percentile for decoding,
protection, atomic storage, preview encoding, and callback time. Report
operational-preview rate, authenticated-packet rate, and byte throughput
separately. M3--M4 estimates incremental Lorenz cost.

Summarize board CSVs with:

```powershell
python scripts/summarize_board_metrics.py data/board/raw/*.csv
```

Never pass the synthetic-verification CSV to that command.

## 16. Troubleshooting

### Board is offline

Confirm power and App Lab state, stop any old app instance, restart the
application before rebooting the board, verify local connectivity, and create
a new phone pairing code after reconnection.

### Phone has Internet but cannot connect

Internet access does not prove local reachability. Disable mobile-data
fallback, guest network, AP isolation, VPN, and automatic network switching.
Confirm that 2.4 and 5 GHz clients are bridged.

### No face callbacks

Confirm `face-detection`, confidence 0.50, frontal light, full face, camera
orientation, and box margin. Do not infer that no frames arrived: negative
frames may be hidden by the callback contract.

### Preview appears but packets do not

M0--M2 are not authenticated. Use M3/M4. Inspect storage capacity,
permissions, the private directory, and `pipeline_error`. A storage failure
removes the stale preview.

### Recovery fails

Verify key, nonce, associated data, profile, NumPy version, and replay state.
The lossy JPEG is never the recovery artifact.

### eMMC fills

Stop the run, preserve its manifest, and apply the declared retention policy.
Production needs quotas, rotation, and alarms before exhaustion.

## 17. Privacy, ethics, and safety

- Start with synthetic material.
- Use consenting adults only when human video is necessary.
- Explain purpose, retention, controller, and deletion date.
- Never publish keys, raw video, original ROIs, or consent forms.
- A missed face remains visible; measure and disclose this limitation.
- M0--M2 are insecure.
- Do not expose the WebUI through public tunnels or port forwarding.
- A small sample cannot support fairness claims.
- Obtain institutional and legal review before human studies or surveillance.

## 18. Reproduction checklist

Before:

- [ ] repository commit recorded;
- [ ] all unit tests pass;
- [ ] board/software versions recorded;
- [ ] condition, scene, resolution, and duration fixed;
- [ ] data policy and retention deadline selected;
- [ ] fresh `run_id` and key;
- [ ] isolated network with no public tunnel;
- [ ] consent/review complete;
- [ ] sufficient storage.

After:

- [ ] CSV and manifest closed;
- [ ] SHA-256 values computed;
- [ ] nonce and identifier uniqueness checked;
- [ ] authentication audit recorded;
- [ ] raw source not retained;
- [ ] private packets kept outside the public repository;
- [ ] results labeled host, pilot, or campaign;
- [ ] deletion scheduled with a responsible person.

## 19. Suggested assignments

1. Change ciphertext, tag, nonce, and associated data one at a time and record
   rejection.
2. Compare M3 and M4 on equal synthetic dimensions without crediting Lorenz
   with security.
3. Generate ten bitstreams and preregister a statistical plan.
4. Implement a local receiver with atomic and idempotent writes.
5. Design a bounded event buffer and calculate worst-case storage.
6. Model timing and packet-size leakage.
7. Instrument a shared source ID to study alignment.
8. Define a new profile with a cryptographically secure generator without
   breaking existing packets.

Every submission should include code, versions, non-sensitive raw data,
success criteria, and a short section titled “What this result does not
demonstrate.”

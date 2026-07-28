"""Arduino App Lab adapter for the official UNO Q face-detection Brick."""

from __future__ import annotations

import base64
import json
import os
import secrets
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from arduino.app_bricks.video_objectdetection import VideoObjectDetection
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import WebSocketCamera
from arduino.app_utils import App, Bridge

from unoq_lorenz.experiment import ExperimentMode, run_experiment_mode
from unoq_lorenz.integrity import audit_authenticated_frame
from unoq_lorenz.metrics import FrameMetrics, append_metrics
from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.packet_store import PacketStore
from unoq_lorenz.protocol import validate_run_id
from unoq_lorenz.run_key import load_or_create_run_key
from unoq_lorenz.telemetry import TelemetryDispatcher, TelemetrySample


def _load_run_config() -> dict[str, object]:
    path = Path(
        os.environ.get(
            "UNOQ_RUN_CONFIG",
            "/app/data/private/run_config.json",
        )
    )
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not read UNO Q run config: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("UNO Q run config must contain one JSON object")
    return payload


run_config = _load_run_config()


def _configured_value(environment_name: str, config_name: str, default: object = ""):
    environment_value = os.environ.get(environment_name)
    if environment_value not in (None, ""):
        return environment_value
    return run_config.get(config_name, default)


def _required_safe_identifier(name: str, config_name: str) -> str:
    value = str(_configured_value(name, config_name, ""))
    if not value:
        raise RuntimeError(
            f"{name} or {config_name!r} in /app/data/private/run_config.json "
            "is required for every physical-board run"
        )
    try:
        return validate_run_id(value)
    except ValueError as error:
        raise RuntimeError(f"invalid {name}: {error}") from error


def _load_condition() -> ExperimentMode:
    try:
        return ExperimentMode(
            str(
                _configured_value(
                    "UNOQ_CONDITION",
                    "condition",
                    ExperimentMode.M4_LORENZ_AEAD.value,
                )
            )
        )
    except ValueError as error:
        allowed = ", ".join(mode.value for mode in ExperimentMode)
        raise RuntimeError(f"UNOQ_CONDITION must be one of: {allowed}") from error


def _load_bbox_margin_fraction() -> float:
    raw = _configured_value(
        "UNOQ_BBOX_MARGIN_FRACTION",
        "bbox_margin_fraction",
        0.10,
    )
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError("UNOQ_BBOX_MARGIN_FRACTION must be numeric") from error
    if not 0.0 <= value <= 0.5:
        raise RuntimeError("UNOQ_BBOX_MARGIN_FRACTION must be within [0, 0.5]")
    return value


def _load_boolean(environment_name: str, config_name: str, default: bool) -> bool:
    raw = _configured_value(environment_name, config_name, default)
    if isinstance(raw, bool):
        return raw
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"{environment_name} or {config_name!r} must be a boolean value"
    )


run_id = _required_safe_identifier("UNOQ_RUN_ID", "run_id")
scene = _required_safe_identifier("UNOQ_SCENE", "scene")
condition = _load_condition()
allow_insecure_ablation = os.environ.get("UNOQ_ALLOW_INSECURE_ABLATION") == "1"
if condition.is_insecure_ablation and not allow_insecure_ablation:
    raise RuntimeError(
        f"{condition.value} is unauthenticated; set "
        "UNOQ_ALLOW_INSECURE_ABLATION=1 only for a registered laboratory run"
    )
bbox_margin_fraction = _load_bbox_margin_fraction()
inline_integrity_audit = _load_boolean(
    "UNOQ_INLINE_INTEGRITY_AUDIT",
    "inline_integrity_audit",
    False,
)
if inline_integrity_audit and not condition.is_authenticated:
    raise RuntimeError(
        "inline integrity audit is available only for M3/M4 authenticated runs"
    )
publication_frame_enabled = _load_boolean(
    "UNOQ_PUBLICATION_FRAME",
    "publication_frame_enabled",
    False,
)
if publication_frame_enabled and not condition.is_authenticated:
    raise RuntimeError(
        "publication-frame capture is available only for M3/M4 authenticated runs"
    )


def _load_publication_arm_file() -> Path | None:
    raw = str(
        _configured_value(
            "UNOQ_PUBLICATION_ARM_FILE",
            "publication_frame_arm_file",
            "",
        )
    ).strip()
    if not raw:
        return None
    path = Path(raw)
    private_root = Path("/app/data/private")
    try:
        path.relative_to(private_root)
    except ValueError as error:
        raise RuntimeError(
            "publication_frame_arm_file must be inside /app/data/private"
        ) from error
    if path == private_root:
        raise RuntimeError(
            "publication_frame_arm_file must name a file inside /app/data/private"
        )
    return path


publication_frame_arm_file = _load_publication_arm_file()

run_key = load_or_create_run_key(
    run_id,
    encoded_key=os.environ.get("UNOQ_MASTER_KEY_B64") or None,
    key_file=os.environ.get("UNOQ_MASTER_KEY_FILE") or None,
    secret_dir=os.environ.get("UNOQ_SECRET_DIR", "/app/data/private"),
)
if run_key.private_path is not None:
    print(
        "UNO Q run key created/loaded from a private file outside the release "
        f"artifacts: {run_key.private_path}"
    )

protector = RoiProtector(run_key.key)
nonces = NonceSequence()
packet_store = PacketStore(
    os.environ.get("UNOQ_PACKET_DIR", "/app/data/packets"),
    run_id=run_id,
    condition=condition.value,
    scene=scene,
    bbox_margin_fraction=bbox_margin_fraction,
    key_fingerprint_sha256=run_key.fingerprint_sha256,
    key_origin=run_key.origin,
    nonce_prefix=nonces.prefix,
    protector=protector,
)
metrics_path = os.environ.get(
    "UNOQ_METRICS_CSV",
    f"/app/data/board/raw/{run_id}_{condition.value}.csv",
)

def _generate_pairing_secret() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


ui = WebUI()
camera_pairing_secret = _generate_pairing_secret()
camera = WebSocketCamera(secret=camera_pairing_secret, encrypt=True)
detection_stream = VideoObjectDetection(
    camera,
    confidence=0.50,
    debounce_sec=0.0,
    camera_preview=True,
)

_frame_counter = 0
_frame_counter_lock = threading.Lock()
_publication_frame_lock = threading.Lock()
_publication_frame_saved = False
_last_cpu_wall = time.perf_counter()
_last_cpu_process = time.process_time()


def _send_to_mcu(sample: TelemetrySample) -> None:
    # Notification is non-blocking at the RPC level and this function itself is
    # called from a bounded worker, never from the detector callback.
    Bridge.notify(
        "record_metrics",
        sample.frame_id,
        sample.linux_protect_us,
        sample.roi_count,
        sample.authenticated_mode,
    )


telemetry = TelemetryDispatcher(_send_to_mcu, capacity=32)


def _next_frame_id() -> int:
    global _frame_counter
    with _frame_counter_lock:
        value = _frame_counter
        _frame_counter += 1
        return value


def _process_cpu_percent() -> float:
    """Return process CPU use since the previous completed callback."""

    global _last_cpu_wall, _last_cpu_process
    wall = time.perf_counter()
    process = time.process_time()
    wall_delta = wall - _last_cpu_wall
    process_delta = process - _last_cpu_process
    _last_cpu_wall = wall
    _last_cpu_process = process
    return 0.0 if wall_delta <= 0.0 else 100.0 * process_delta / wall_delta


def _system_memory_percent() -> float:
    """Read Linux memory use without adding a non-Brick dependency."""

    try:
        fields = {}
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                name, raw = line.split(":", 1)
                fields[name] = int(raw.strip().split()[0])
        total = fields["MemTotal"]
        available = fields["MemAvailable"]
        return 100.0 * (total - available) / total
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return float("nan")


def _process_rss_kib() -> int:
    """Return resident memory from Linux procfs, or -1 when unavailable."""

    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return -1


def _store_publication_frame_once(jpeg: np.ndarray) -> Path | None:
    """Persist one protected preview and never retain the decoded source frame."""

    global _publication_frame_saved
    if not publication_frame_enabled:
        return None
    with _publication_frame_lock:
        if _publication_frame_saved:
            return None
        if (
            publication_frame_arm_file is not None
            and not publication_frame_arm_file.is_file()
        ):
            return None
        output_dir = Path("/app/data/board/publication")
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{run_id}_protected_preview.jpg"
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(jpeg.tobytes())
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                destination.unlink()
            except OSError:
                pass
            raise
        if publication_frame_arm_file is not None:
            publication_frame_arm_file.unlink(missing_ok=True)
        _publication_frame_saved = True
        print(f"Protected publication frame saved: {destination}")
        return destination


def _face_boxes(detections: dict) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for item in detections.get("face", []):
        if "bounding_box_xyxy" not in item:
            continue
        x0, y0, x1, y1 = (
            int(value) for value in item["bounding_box_xyxy"]
        )
        width = max(0, x1 - x0)
        height = max(0, y1 - y0)
        margin_x = int(round(width * bbox_margin_fraction))
        margin_y = int(round(height * bbox_margin_fraction))
        boxes.append((x0 - margin_x, y0 - margin_y, x1 + margin_x, y1 + margin_y))
    return boxes


def _experiment_state() -> dict[str, object]:
    return {
        "run_id": run_id,
        "condition": condition.value,
        "authenticated_mode": condition.is_authenticated,
        "bbox_margin_fraction": bbox_margin_fraction,
        "inline_integrity_audit": inline_integrity_audit,
        "publication_frame_enabled": publication_frame_enabled,
        "publication_frame_requires_arm_file": (
            publication_frame_arm_file is not None
        ),
        "preview_recoverable": False,
        "payload_policy": (
            "authenticated packets persist outside the browser"
            if condition.is_authenticated
            else "no authenticated packet: insecure laboratory ablation"
        ),
    }


def _camera_pairing_state() -> dict[str, object]:
    return {
        "client_name": camera.name,
        "status": camera.status,
        "secret": camera_pairing_secret,
        "protocol": camera.protocol,
        "ip": camera.ip,
        "port": camera.port,
        "transport_encrypted": True,
        "source": "smartphone_camera",
    }


def _on_camera_status(event_type: str, data: dict | None) -> None:
    payload = _camera_pairing_state()
    payload["status"] = event_type
    if isinstance(data, dict) and data.get("client_name"):
        payload["client_name"] = data["client_name"]
    ui.send_message("camera_status", payload)


def _on_ui_connect(session_id: str) -> None:
    ui.send_message("experiment_state", _experiment_state(), room=session_id)
    ui.send_message("camera_pairing", _camera_pairing_state(), room=session_id)


def _send_pipeline_error(frame_id: int | None, error_code: str) -> None:
    ui.send_message(
        "pipeline_error",
        {
            **_experiment_state(),
            "frame_id": frame_id,
            "error_code": error_code,
        },
    )


def process_detections(detections: dict, *, frame: bytes | None = None) -> None:
    """Create one protected output without silently losing its ROI packets."""

    local_frame_id = _next_frame_id()
    callback_started = time.perf_counter()
    try:
        if not frame:
            raise ValueError("callback did not include JPEG bytes")

        decode_started = time.perf_counter()
        encoded = np.frombuffer(frame, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        decode_ms = (time.perf_counter() - decode_started) * 1_000.0
        if image is None:
            raise ValueError("OpenCV could not decode callback JPEG")

        boxes = _face_boxes(detections)
        protect_started = time.perf_counter()
        result = run_experiment_mode(
            image,
            boxes,
            run_id=run_id,
            frame_id=local_frame_id,
            mode=condition,
            protector=protector,
            nonces=nonces,
            allow_insecure_ablation=allow_insecure_ablation,
        )
        protect_ms = (time.perf_counter() - protect_started) * 1_000.0

        packet_store_ms = 0.0
        packet_bytes = 0
        payload_persisted = False
        if condition.is_authenticated:
            if not result.packets:
                raise RuntimeError(
                    "authenticated callback produced no recoverable ROI packet"
                )
            store_started = time.perf_counter()
            stored = packet_store.store_frame(result.packets)
            packet_store_ms = (time.perf_counter() - store_started) * 1_000.0
            packet_bytes = stored.serialized_bytes
            payload_persisted = True

        exact_recovery_checks = 0
        exact_recovery_passes = 0
        tamper_checks = 0
        tamper_rejections = 0
        integrity_audit_ms = 0.0
        if inline_integrity_audit:
            audit_started = time.perf_counter()
            audit = audit_authenticated_frame(
                image,
                result.packets,
                protector=protector,
            )
            integrity_audit_ms = (
                time.perf_counter() - audit_started
            ) * 1_000.0
            exact_recovery_checks = audit.exact_recovery_checks
            exact_recovery_passes = audit.exact_recovery_passes
            tamper_checks = audit.tamper_checks
            tamper_rejections = audit.tamper_rejections

        encode_started = time.perf_counter()
        ok, jpeg = cv2.imencode(".jpg", result.preview)
        preview_encode_ms = (time.perf_counter() - encode_started) * 1_000.0
        if not ok:
            raise RuntimeError("OpenCV could not encode the operational preview")
        _store_publication_frame_once(jpeg)

        channels = 1 if image.ndim == 2 else int(image.shape[2])
        roi_spatial_pixels = sum(
            (x1 - x0) * (y1 - y0)
            for x0, y0, x1, y1 in result.accepted_boxes
        )
        roi_bytes = roi_spatial_pixels * channels
        telemetry_enqueued = telemetry.submit(
            TelemetrySample(
                frame_id=local_frame_id,
                linux_protect_us=max(0, int(round(protect_ms * 1_000.0))),
                roi_count=len(result.accepted_boxes),
                authenticated_mode=condition.is_authenticated,
            )
        )
        completed_monotonic = time.monotonic()
        callback_core_ms = (time.perf_counter() - callback_started) * 1_000.0
        metrics = FrameMetrics(
            run_id=run_id,
            scene=scene,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            timestamp_monotonic_s=completed_monotonic,
            frame_id=local_frame_id,
            condition=condition.value,
            input_width=int(image.shape[1]),
            input_height=int(image.shape[0]),
            channels=channels,
            bbox_margin_fraction=bbox_margin_fraction,
            roi_count=len(result.accepted_boxes),
            roi_spatial_pixels=roi_spatial_pixels,
            roi_bytes=roi_bytes,
            input_jpeg_bytes=len(frame),
            preview_jpeg_bytes=int(jpeg.size),
            packet_count=len(result.packets),
            packet_bytes=packet_bytes,
            decode_ms=decode_ms,
            protect_ms=protect_ms,
            packet_store_ms=packet_store_ms,
            inline_integrity_audit_enabled=int(inline_integrity_audit),
            exact_recovery_checks=exact_recovery_checks,
            exact_recovery_passes=exact_recovery_passes,
            tamper_checks=tamper_checks,
            tamper_rejections=tamper_rejections,
            integrity_audit_ms=integrity_audit_ms,
            preview_encode_ms=preview_encode_ms,
            callback_core_ms=callback_core_ms,
            process_cpu_percent=_process_cpu_percent(),
            process_rss_kib=_process_rss_kib(),
            system_memory_percent=_system_memory_percent(),
            # The official Brick exposes neither source-frame IDs nor its
            # internal callback-drop count through this callback contract.
            source_dropped_callbacks=-1,
            source_frame_id_available=0,
            telemetry_enqueued=int(telemetry_enqueued),
        )
        append_metrics(metrics_path, metrics)

        # Only after packet persistence and evidence logging succeed do we
        # announce a fresh operational preview to the browser.
        ui.send_message(
            "protected_preview",
            {
                **_experiment_state(),
                "frame_id": local_frame_id,
                "jpeg_b64": base64.b64encode(jpeg).decode("ascii"),
                "roi_count": len(result.accepted_boxes),
                "protect_ms": round(protect_ms, 3),
                "packet_count": len(result.packets),
                "payload_persisted": payload_persisted,
            },
        )
    except Exception as error:
        # Future/callback exceptions in the official Brick can otherwise be
        # hard to observe.  Report a type-only diagnostic and fail the UI shut.
        print(
            f"UNO Q pipeline error on local frame {local_frame_id}: "
            f"{type(error).__name__}: {error}"
        )
        _send_pipeline_error(local_frame_id, type(error).__name__)


camera.on_status_changed(_on_camera_status)
ui.on_connect(_on_ui_connect)
detection_stream.on_detect_all(process_detections)
App.run()

"""Authenticated delivery of board-persisted frame bundles to a laptop."""

from __future__ import annotations

import hashlib
import hmac
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .packet_store import StoredFrameBundle, parse_frame_bundle_bytes


AUTH_SCHEME = "unoq-hmac-sha256-v1"


@dataclass(frozen=True)
class DeliverySnapshot:
    enqueued: int
    delivered: int
    failed: int
    queue_full: int
    pending: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ReceivedFrameBundle:
    path: Path
    sha256: str
    run_id: str
    frame_id: int
    packet_count: int
    duplicate: bool


def load_receiver_token(path: str | Path) -> bytes:
    source = Path(path)
    try:
        token = source.read_bytes().strip()
    except OSError as error:
        raise ValueError(f"could not read laptop-receiver token: {source}") from error
    if len(token) < 32:
        raise ValueError("laptop-receiver token must contain at least 32 bytes")
    if len(token) > 1024 or any(byte in b"\r\n\t " for byte in token):
        raise ValueError("laptop-receiver token has an invalid representation")
    return token


def _signature_input(timestamp: str, digest: str, payload: bytes) -> bytes:
    return (
        timestamp.encode("ascii")
        + b"\n"
        + digest.encode("ascii")
        + b"\n"
        + payload
    )


def build_request_auth(
    token: bytes,
    payload: bytes,
    *,
    timestamp: int | None = None,
) -> dict[str, str]:
    if len(token) < 32:
        raise ValueError("receiver token must contain at least 32 bytes")
    timestamp_text = str(int(time.time()) if timestamp is None else int(timestamp))
    digest = hashlib.sha256(payload).hexdigest()
    signature = hmac.new(
        token,
        _signature_input(timestamp_text, digest, payload),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-UNOQ-Auth": AUTH_SCHEME,
        "X-UNOQ-Timestamp": timestamp_text,
        "X-UNOQ-SHA256": digest,
        "X-UNOQ-Signature": signature,
    }


def verify_request_auth(
    token: bytes,
    payload: bytes,
    headers: dict[str, str],
    *,
    now: int | None = None,
    max_clock_skew_seconds: int = 300,
) -> str:
    if headers.get("X-UNOQ-Auth") != AUTH_SCHEME:
        raise ValueError("unsupported receiver authentication scheme")
    timestamp_text = headers.get("X-UNOQ-Timestamp", "")
    try:
        timestamp = int(timestamp_text)
    except ValueError as error:
        raise ValueError("invalid receiver timestamp") from error
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > max_clock_skew_seconds:
        raise ValueError("receiver timestamp is outside the accepted clock window")
    supplied_digest = headers.get("X-UNOQ-SHA256", "")
    actual_digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(supplied_digest, actual_digest):
        raise ValueError("packet-bundle digest mismatch")
    supplied_signature = headers.get("X-UNOQ-Signature", "")
    expected_signature = hmac.new(
        token,
        _signature_input(timestamp_text, actual_digest, payload),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("packet-bundle request signature mismatch")
    return actual_digest


def _publish_new_file(destination: Path, payload: bytes) -> bool:
    """Publish bytes atomically; return False for an identical retry."""

    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(
            payload
        ).digest():
            return False
        raise FileExistsError(
            f"frame identity already exists with different bytes: {destination}"
        )
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(
                payload
            ).digest():
                return False
            raise
        return True
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


class ReceivedBundleStore:
    """Atomic, idempotent storage for bundles accepted by the laptop."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, payload: bytes, expected_sha256: str) -> ReceivedFrameBundle:
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise ValueError("received body does not match its authenticated digest")
        info, _ = parse_frame_bundle_bytes(payload)
        run_dir = self.root / info.run_id
        run_dir.mkdir(mode=0o700, exist_ok=True)
        destination = run_dir / f"frame_{info.frame_id:010d}.json"
        created = _publish_new_file(destination, payload)
        return ReceivedFrameBundle(
            path=destination,
            sha256=actual_sha256,
            run_id=info.run_id,
            frame_id=info.frame_id,
            packet_count=info.packet_count,
            duplicate=not created,
        )


class PermanentDeliveryError(RuntimeError):
    """A request that should not be retried without a configuration change."""


Sender = Callable[[str, bytes, dict[str, str], float], int]


def _http_sender(
    url: str,
    payload: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> int:
    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status)
    except HTTPError as error:
        if error.code not in {408, 425, 429} and error.code < 500:
            raise PermanentDeliveryError(
                f"laptop receiver rejected the request with HTTP {error.code}"
            ) from error
        raise


class LaptopBundleDispatcher:
    """Bounded background delivery; board-local evidence remains authoritative."""

    def __init__(
        self,
        url: str,
        token: bytes,
        *,
        capacity: int = 32,
        timeout_seconds: float = 5.0,
        max_attempts: int = 8,
        sender: Sender | None = None,
    ) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("laptop receiver URL must use http:// or https://")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("laptop receiver URL must not contain credentials or fragments")
        if len(token) < 32:
            raise ValueError("receiver token must contain at least 32 bytes")
        if not 1 <= capacity <= 1024:
            raise ValueError("laptop delivery queue capacity must be within [1, 1024]")
        if not 1 <= max_attempts <= 20:
            raise ValueError("laptop delivery attempts must be within [1, 20]")
        self.url = url
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._sender = sender or _http_sender
        self._queue: queue.Queue[StoredFrameBundle] = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._enqueued = 0
        self._delivered = 0
        self._failed = 0
        self._queue_full = 0
        self._pending = 0
        self._worker = threading.Thread(
            target=self._run,
            name="unoq-laptop-bundle-dispatch",
            daemon=True,
        )
        self._worker.start()

    def submit(self, bundle: StoredFrameBundle) -> bool:
        with self._lock:
            try:
                self._queue.put_nowait(bundle)
            except queue.Full:
                self._queue_full += 1
                return False
            self._enqueued += 1
            self._pending += 1
        return True

    def snapshot(self) -> DeliverySnapshot:
        with self._lock:
            return DeliverySnapshot(
                enqueued=self._enqueued,
                delivered=self._delivered,
                failed=self._failed,
                queue_full=self._queue_full,
                pending=self._pending,
            )

    def wait_until_idle(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.snapshot().pending == 0:
                return True
            time.sleep(0.01)
        return self.snapshot().pending == 0

    def _deliver(self, bundle: StoredFrameBundle) -> None:
        payload = bundle.path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(digest, bundle.sha256):
            raise PermanentDeliveryError("board-local bundle digest changed before delivery")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": digest,
            "X-UNOQ-Run-ID": bundle.run_id,
            "X-UNOQ-Frame-ID": str(bundle.frame_id),
            **build_request_auth(self._token, payload),
        }
        status = self._sender(self.url, payload, headers, self._timeout_seconds)
        if status not in {200, 201, 202}:
            raise PermanentDeliveryError(
                f"laptop receiver returned unexpected HTTP status {status}"
            )

    def _run(self) -> None:
        while True:
            bundle = self._queue.get()
            delivered = False
            try:
                for attempt in range(self._max_attempts):
                    try:
                        self._deliver(bundle)
                        delivered = True
                        break
                    except PermanentDeliveryError:
                        break
                    except Exception:
                        if attempt + 1 < self._max_attempts:
                            time.sleep(min(10.0, 0.25 * (2**attempt)))
            finally:
                with self._lock:
                    if delivered:
                        self._delivered += 1
                    else:
                        self._failed += 1
                    self._pending -= 1
                self._queue.task_done()

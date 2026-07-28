"""Bounded asynchronous forwarding of compact Linux metrics to the MCU."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TelemetrySample:
    frame_id: int
    linux_protect_us: int
    roi_count: int
    authenticated_mode: bool


class TelemetryDispatcher:
    """Keep Bridge I/O outside the detector callback and bound backpressure."""

    def __init__(
        self,
        sender: Callable[[TelemetrySample], None],
        *,
        capacity: int = 32,
    ) -> None:
        if capacity <= 0:
            raise ValueError("telemetry capacity must be positive")
        self._sender = sender
        self._queue: queue.Queue[TelemetrySample | None] = queue.Queue(capacity)
        self._lock = threading.Lock()
        self._sent = 0
        self._failed = 0
        self._dropped = 0
        self._thread = threading.Thread(
            target=self._worker,
            name="unoq-bridge-telemetry",
            daemon=True,
        )
        self._thread.start()

    def submit(self, sample: TelemetrySample) -> bool:
        try:
            self._queue.put_nowait(sample)
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False
        return True

    def _worker(self) -> None:
        while True:
            sample = self._queue.get()
            try:
                if sample is None:
                    return
                self._sender(sample)
                with self._lock:
                    self._sent += 1
            except Exception:
                with self._lock:
                    self._failed += 1
            finally:
                self._queue.task_done()

    @property
    def counters(self) -> dict[str, int]:
        with self._lock:
            return {
                "sent": self._sent,
                "failed": self._failed,
                "dropped": self._dropped,
                "queued": self._queue.qsize(),
            }

    def close(self, *, timeout_s: float = 1.0) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            return
        self._thread.join(timeout_s)

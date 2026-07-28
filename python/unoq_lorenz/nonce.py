"""Thread-safe nonce allocation for one ephemeral experiment session."""

from __future__ import annotations

import os
import threading
from typing import NamedTuple


class NonceAllocation(NamedTuple):
    """One atomic packet identifier and its matching 96-bit nonce."""

    counter: int
    nonce: bytes


class NonceSequence:
    """Allocate 96-bit nonces as a random 64-bit prefix plus uint32 counter.

    The sequence is scoped to one run key. The protocol requires a freshly
    generated 256-bit key for every run; a sequence must never be shared across
    keys or reset under the same key.
    """

    def __init__(self, prefix: bytes | None = None, *, start: int = 0) -> None:
        if prefix is not None and not isinstance(prefix, (bytes, bytearray, memoryview)):
            raise TypeError("nonce prefix must be bytes-like")
        self._prefix = os.urandom(8) if prefix is None else bytes(prefix)
        if len(self._prefix) != 8:
            raise ValueError("nonce prefix must contain exactly eight bytes")
        if not isinstance(start, int) or isinstance(start, bool):
            raise TypeError("counter start must be an integer")
        if start < 0 or start >= 2**32:
            raise ValueError("counter start is outside uint32 range")
        self._counter = start
        self._lock = threading.Lock()

    @property
    def prefix(self) -> bytes:
        return self._prefix

    @property
    def next_counter(self) -> int:
        with self._lock:
            return self._counter

    def allocate(self) -> NonceAllocation:
        """Atomically return the packet counter and corresponding nonce."""

        with self._lock:
            if self._counter >= 2**32:
                raise OverflowError("nonce counter exhausted")
            counter = self._counter
            nonce = self._prefix + counter.to_bytes(4, "big")
            self._counter += 1
            return NonceAllocation(counter, nonce)

    def next(self) -> bytes:
        """Compatibility helper for ablations that do not emit packets."""

        return self.allocate().nonce

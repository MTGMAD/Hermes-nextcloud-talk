"""Bounded in-memory idempotency state for inbound Talk events."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Literal

RecordState = Literal["processing", "response_ready", "delivering", "delivered", "failed"]
ClaimState = Literal[
    "new",
    "processing",
    "response_ready",
    "delivering",
    "delivered",
    "failed",
    "capacity_exhausted",
]


@dataclass
class _Record:
    token: str
    expires_at: float
    state: RecordState
    response: str | None = None


@dataclass(frozen=True)
class Claim:
    """The safe next action and ownership token for one idempotency key."""

    state: ClaimState
    token: str | None = None
    response: str | None = None


class InMemoryIdempotencyStore:
    """Atomic TTL cache that prevents repeated Hermes execution in one process."""

    def __init__(self, *, ttl_seconds: float = 600, max_entries: int = 10_000) -> None:
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("idempotency limits must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._records: dict[str, _Record] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str) -> Claim:
        """Atomically reserve an event or return its current retry-safe state."""
        async with self._lock:
            now = time.monotonic()
            self._purge_expired_inactive(now)
            record = self._records.get(key)
            if record is None:
                if len(self._records) >= self._max_entries:
                    return Claim(state="capacity_exhausted")
                token = uuid.uuid4().hex
                self._records[key] = _Record(
                    token=token,
                    expires_at=now + self._ttl_seconds,
                    state="processing",
                )
                return Claim(state="new", token=token)
            return Claim(
                state=record.state,
                token=record.token,
                response=record.response,
            )

    async def save_response(self, key: str, token: str, response: str) -> None:
        """Persist a generated response before attempting external delivery."""
        async with self._lock:
            record = self._require_owner(key, token, "processing")
            record.response = response
            record.state = "response_ready"

    async def reserve_delivery(self, key: str, token: str) -> str:
        """Acquire the single outbound-delivery lease for a saved response."""
        async with self._lock:
            record = self._require_owner(key, token, "response_ready")
            if record.response is None:
                raise RuntimeError("response was not saved")
            record.state = "delivering"
            return record.response

    async def release_delivery(self, key: str, token: str) -> None:
        """Make a saved response retryable after a failed delivery attempt."""
        async with self._lock:
            record = self._require_owner(key, token, "delivering")
            record.state = "response_ready"

    async def mark_failed(self, key: str, token: str) -> None:
        """Retain a failed execution as a bounded, non-retryable event record."""
        async with self._lock:
            record = self._require_owner(key, token, "processing")
            record.state = "failed"

    async def mark_delivered(self, key: str, token: str) -> None:
        """Mark an outbound delivery as complete, preventing future repeats."""
        async with self._lock:
            record = self._require_owner(key, token, "delivering")
            record.state = "delivered"

    def _require_owner(self, key: str, token: str, expected_state: RecordState) -> _Record:
        record = self._records.get(key)
        if record is None or record.token != token or record.state != expected_state:
            raise RuntimeError("idempotency claim is no longer owned")
        return record

    def _purge_expired_inactive(self, now: float) -> None:
        for key, record in list(self._records.items()):
            if record.expires_at <= now and record.state in {
                "response_ready",
                "delivered",
                "failed",
            }:
                del self._records[key]

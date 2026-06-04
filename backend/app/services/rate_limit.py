"""Lightweight in-memory rate limiter.

Sliding-window per-key. Resets on process restart, which is fine for the
short windows we care about (per-hour caps on a couple of expensive
endpoints). Not a horizontal-scale solution — single-process gunicorn
deployment assumed. If/when we go multi-worker, swap the storage for
Redis but keep the API.
"""
from __future__ import annotations

from collections import deque
from time import monotonic
from typing import Deque

from fastapi import HTTPException


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, Deque[float]] = {}

    def check(self, key: str, limit: int, window_sec: int) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds).

        retry_after is 0 when allowed. Updates the bucket on success.
        """
        now = monotonic()
        bucket = self._buckets.setdefault(key, deque())
        cutoff = now - window_sec
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = bucket[0] + window_sec - now
            return False, max(retry_after, 1.0)
        bucket.append(now)
        return True, 0.0


class FailureTracker:
    """Counts *failures* per key in a sliding window — for login-style lockout
    ("N wrong attempts ⇒ cooldown"), which is different from
    SlidingWindowLimiter (which caps *all* calls regardless of outcome).

    Used by the self-service availability PIN check: a successful verify clears
    the key; a wrong PIN records a failure; once `max_failures` land inside the
    window the player+IP is locked out for the rest of the window. Same
    single-process, in-memory caveat as the limiter above.
    """

    def __init__(self) -> None:
        self._failures: dict[str, Deque[float]] = {}

    @staticmethod
    def _trim(bucket: Deque[float], cutoff: float) -> None:
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def count(self, key: str, window_sec: int) -> int:
        bucket = self._failures.get(key)
        if not bucket:
            return 0
        self._trim(bucket, monotonic() - window_sec)
        if not bucket:
            self._failures.pop(key, None)
            return 0
        return len(bucket)

    def record(self, key: str, window_sec: int) -> None:
        now = monotonic()
        bucket = self._failures.setdefault(key, deque())
        self._trim(bucket, now - window_sec)
        bucket.append(now)

    def retry_after(self, key: str, window_sec: int) -> float:
        bucket = self._failures.get(key)
        if not bucket:
            return 0.0
        return max(bucket[0] + window_sec - monotonic(), 0.0)

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)


_limiter = SlidingWindowLimiter()
_failures = FailureTracker()


def enforce(key: str, limit: int, window_sec: int, detail: str | None = None) -> None:
    """Raise 429 if `key` has hit `limit` calls within `window_sec`.

    Call at the top of an endpoint handler. `key` should include the user
    id (or org id) and a stable name for the endpoint, e.g.
    `f"hard-refresh:{org_id}"`.
    """
    ok, retry_after = _limiter.check(key, limit, window_sec)
    if not ok:
        retry_int = int(retry_after) + 1
        raise HTTPException(
            status_code=429,
            detail=detail or f"Too many requests — try again in {retry_int}s",
            headers={"Retry-After": str(retry_int)},
        )


def assert_not_locked(key: str, max_failures: int, window_sec: int, detail: str | None = None) -> None:
    """Raise 429 if `key` has already recorded `max_failures` within the window.

    The lockout half of a fail-counting gate — pair with `record_failure` (on a
    wrong attempt) and `clear_failures` (on success). Call before checking the
    secret so a locked-out caller never gets another guess.
    """
    if _failures.count(key, window_sec) >= max_failures:
        retry_int = int(_failures.retry_after(key, window_sec)) + 1
        raise HTTPException(
            status_code=429,
            detail=detail or f"Too many attempts — try again in {retry_int}s",
            headers={"Retry-After": str(retry_int)},
        )


def record_failure(key: str, window_sec: int) -> None:
    _failures.record(key, window_sec)


def clear_failures(key: str) -> None:
    _failures.clear(key)

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


_limiter = SlidingWindowLimiter()


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

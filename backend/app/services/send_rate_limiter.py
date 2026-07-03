"""Process-global async pacer for outbound SES sends.

AWS grants this account a **maximum send rate** (14 messages/second) that is
shared across everything we send: every club's campaigns, the BetterCricket
marketing org, and any future transactional mail. Exceeding it makes SES return
``Throttling`` (429), and our send loop marks those recipients permanently
failed — so pacing UNDER the ceiling is how we avoid silently dropping mail.

This is a single token-bucket-ish pacer, guarded by one ``asyncio.Lock`` so the
spacing sleep serialises acquisitions. Because we run a **single uvicorn worker**
(see the Dockerfile CMD), this one in-process bucket bounds the whole account.
If the deployment ever grows to N workers, divide ``ses_max_send_rate`` by N (or
move this to Redis) — the module docstring in rate_limit.py has the same caveat.

Usage — call ``await acquire()`` immediately before each ``provider.send()``:

    from app.services.send_rate_limiter import send_limiter
    async with sem:                 # concurrency cap (unchanged)
        await send_limiter.acquire()  # rate cap (new)
        res = await provider.send(msg)

The pacer is a no-op for the console provider path in practice (nothing leaves
the building), but acquiring is cheap, so callers don't special-case it.
"""
from __future__ import annotations

import asyncio
from time import monotonic

from app.config.settings import settings


class SendRateLimiter:
    """Spaces acquisitions to at most ``rate`` per second, account-wide.

    Keeps the timestamp of the last grant; each ``acquire`` waits until at least
    ``1/rate`` seconds have passed since the previous one. Simple, exact, and
    fair (FIFO under the lock), which is what a steady blast wants — no bursty
    token accumulation that could momentarily exceed the AWS per-second ceiling.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    def _min_interval(self) -> float:
        # The live rate is the super-admin-managed platform setting (warm cache,
        # sync, no DB on the hot path); it falls back to the env seed default
        # until warmed. Lazy import avoids any startup import cycle.
        try:
            from app.services import platform_settings
            rate = int(platform_settings.cached_send_rate())
        except Exception:
            try:
                rate = int(getattr(settings, "ses_max_send_rate", 0)) or 13
            except (TypeError, ValueError):
                rate = 13
        rate = max(1, rate)
        return 1.0 / rate

    async def acquire(self) -> None:
        interval = self._min_interval()
        async with self._lock:
            now = monotonic()
            # If we're behind schedule (idle gap), send immediately; otherwise
            # wait out the remaining slice of this slot.
            start = self._next_at if self._next_at > now else now
            wait = start - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_at = start + interval


# Process-global singleton — one bucket for the whole account.
send_limiter = SendRateLimiter()

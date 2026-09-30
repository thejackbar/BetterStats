"""Spaces outbound calls so an upstream sees an ongoing trickle, not bursts.

The teaser crawler used to fire a small batch every five minutes: a burst, then
nothing, then another burst. This is the other shape. Every caller asks for a
slot (`wait`), slots are handed out one gap apart, and the gap is jittered so
the load wobbles a little instead of ticking like a metronome.

* **The rate is an AVERAGE and the jitter is symmetric.** A gap is
  ``(1 / rate)`` scaled by a random factor in ``1 +/- jitter``, so over any
  stretch of a few dozen calls the rate is the one asked for. Individual gaps
  are as short as ``(1 - jitter) / rate``.
* **Slots are reserved, not queued behind a lock.** ``reserve`` is synchronous
  (no await between reading and moving the next slot), so on one event loop two
  callers can never be handed the same instant, and any number of concurrent
  tasks share ONE budget. Give every task in a crawl the same pacer and the
  crawl has one rate, however many clubs it is working at once.
* **Idle time is not banked.** A slot is never earlier than "now", so a pacer
  that has sat quiet for an hour does not release an hour's worth of calls in
  one go. That is the whole difference from a token bucket, and it is the
  property that keeps this from becoming a burst again.
* **The rate can change while it runs.** ``set_rate`` takes effect from the next
  reservation, which is how the operator's setting is picked up without a
  restart.

Nothing here imports the database or the app: the clock, the sleep and the
random source are all arguments, so the arithmetic is checked without waiting.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Awaitable, Callable

DEFAULT_JITTER = 0.25


class CallPacer:
    def __init__(self, rate: float, *, jitter: float = DEFAULT_JITTER,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 rng: Callable[[], float] = random.random):
        if not 0 <= jitter < 1:
            raise ValueError("jitter must be in [0, 1)")
        self._jitter = jitter
        self._clock, self._sleep, self._rng = clock, sleep, rng
        self._rate = 0.0
        self._next = 0.0
        self.set_rate(rate)

    @property
    def rate(self) -> float:
        return self._rate

    def set_rate(self, rate: float) -> None:
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise ValueError("rate must be a positive number of calls per second")
        self._rate = float(rate)

    def _gap(self) -> float:
        return (1.0 / self._rate) * (1.0 + self._jitter * (2.0 * self._rng() - 1.0))

    def reserve(self) -> float:
        """Claim the next slot and return how many seconds from now it is."""
        now = self._clock()
        at = max(now, self._next)
        self._next = at + self._gap()
        return at - now

    async def wait(self) -> None:
        delay = self.reserve()
        if delay > 0:
            await self._sleep(delay)

"""A small in-process rate limiter for the endpoints that cost real money.

The demo is meant to be handed to strangers on a public URL, and two endpoints spend
something when called: scenario injection consumes LLM tokens from a free-tier budget
of a few thousand per minute, and the live CAMARA check consumes sandbox quota. Left
open, a single enthusiastic visitor — or a crawler — exhausts both and the demo stops
demonstrating anything.

Deliberately simple: a fixed window per client, in memory, no dependencies. There is
one process and the limits are generous, so a token bucket in Redis would be more
machinery than the problem deserves.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, name: str) -> None:
        self.limit = limit
        self.window = window_seconds
        self.name = name
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client(self, request: Request) -> str:
        # Behind Render/Fly the real client is in X-Forwarded-For — but which element
        # matters. A proxy *appends* the peer it saw, so the last element is the one it
        # observed and the only one it wrote; everything before it was supplied by the
        # caller. Reading the first element means a caller who sends a fresh random
        # value on every request gets a fresh bucket every time, which makes both
        # limiters no-ops against anyone who has read this file — and this repo is
        # public. It also turns `_hits` into an unbounded attacker-keyed dict.
        #
        # Exactly one trusted proxy sits in front of us (Render), so: last element.
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            parts = [p.strip() for p in fwd.split(",") if p.strip()]
            if parts:
                return parts[-1]
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        now = time.monotonic()
        key = self._client(request)
        hits = self._hits[key]
        hits[:] = [h for h in hits if now - h < self.window]
        if len(hits) >= self.limit:
            retry = int(self.window - (now - hits[0])) + 1
            raise HTTPException(
                429,
                f"Too many {self.name} requests — try again in {retry}s. "
                "This is a shared demo running on free-tier API quota.",
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)

    # Keeps the dict from growing forever on a long-lived deployment.
    def prune(self) -> None:
        now = time.monotonic()
        for key in list(self._hits):
            self._hits[key][:] = [h for h in self._hits[key] if now - h < self.window]
            if not self._hits[key]:
                del self._hits[key]


class DailyBudget:
    """A process-wide ceiling that no per-client key can route around.

    The per-client limiter answers "is one visitor being greedy". It does not answer
    "has the whole day's quota gone", and those are different questions: the Groq free
    tier is 200k tokens per *day*, and four investigations a minute — the honest,
    within-limits rate — drains it in about forty minutes of steady clicking. Every
    client can be individually well-behaved while the demo still goes dark before
    judging.

    Deliberately keyed on nothing at all. Anything derived from the request can be
    spoofed, and the budget being protected is shared, so the counter should be too.
    """

    def __init__(self, limit: int, name: str) -> None:
        self.limit = limit
        self.name = name
        self._day: str = ""
        self._count = 0

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    @property
    def remaining(self) -> int:
        return self.limit - self._count if self._day == self._today() else self.limit

    def check(self) -> None:
        today = self._today()
        if self._day != today:
            self._day, self._count = today, 0
        if self._count >= self.limit:
            raise HTTPException(
                429,
                f"The shared daily {self.name} budget for this demo is spent "
                f"({self.limit}/day). It resets at 00:00 UTC.",
            )
        self._count += 1


# One investigation costs ~1.3k LLM tokens against a shared 8k/min budget, and a
# retried one costs it twice. Six per minute sits exactly on the ceiling with no room
# for the retries, so cap at four and keep the headroom.
inject_limiter = RateLimiter(limit=4, window_seconds=60.0, name="scenario")
# Each live check is several round trips to Nokia's sandbox.
live_check_limiter = RateLimiter(limit=10, window_seconds=60.0, name="live CAMARA")

# ~1.3k tokens an investigation against 200k/day leaves room for roughly 150 runs.
# Stopping at 120 keeps a rehearsal margin in reserve for the day of the demo.
inject_budget = DailyBudget(limit=120, name="scenario")
live_check_budget = DailyBudget(limit=300, name="live CAMARA")

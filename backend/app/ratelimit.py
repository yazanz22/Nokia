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
        # Behind Render/Fly the real client is in X-Forwarded-For.
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
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


# One investigation costs ~1.3k LLM tokens against a shared 8k/min budget, and a
# retried one costs it twice. Six per minute sits exactly on the ceiling with no room
# for the retries, so cap at four and keep the headroom.
inject_limiter = RateLimiter(limit=4, window_seconds=60.0, name="scenario")
# Each live check is two round trips to Nokia's sandbox.
live_check_limiter = RateLimiter(limit=10, window_seconds=60.0, name="live CAMARA")

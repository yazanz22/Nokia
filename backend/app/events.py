"""A tiny in-process async pub/sub bus.

Producers (simulator, anomaly detector, agent) call ``bus.publish(event)``.
Consumers (each dashboard WebSocket) hold a ``Subscription`` and ``await`` events.
No external broker — everything runs in one process for the demo.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from .models import WsEvent


class Subscription:
    def __init__(self, bus: "EventBus", maxsize: int = 1000) -> None:
        self._bus = bus
        self._queue: asyncio.Queue[WsEvent] = asyncio.Queue(maxsize=maxsize)

    def _put(self, event: WsEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event to keep the stream live rather than block producers.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(event)

    async def __aiter__(self) -> AsyncIterator[WsEvent]:
        try:
            while True:
                yield await self._queue.get()
        finally:
            self._bus.unsubscribe(self)


class EventBus:
    def __init__(self) -> None:
        self._subs: set[Subscription] = set()

    def subscribe(self) -> Subscription:
        sub = Subscription(self)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subs.discard(sub)

    def publish(self, event: WsEvent) -> None:
        for sub in list(self._subs):
            sub._put(event)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


bus = EventBus()

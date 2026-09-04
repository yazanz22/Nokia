"""A tiny in-process async pub/sub bus.

Producers (simulator, anomaly detector, agent) call ``bus.publish(event)``.
Consumers (each dashboard WebSocket) hold a ``Subscription`` and ``await`` frames
that are already serialised — the bus dumps a ``WsEvent`` once and hands the same
JSON-ready dict to everyone. No external broker; everything runs in one process
for the demo.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from .models import WsEvent

# The deployed demo is a single public URL with no authentication, so how many
# dashboards attach is whatever the internet decides. Each subscriber costs a
# 1000-slot queue, a full ``store.snapshot()`` at connect time, and a slot in
# every fan-out for the life of the socket — on a 512MB instance a shared link,
# a crawler or a reconnect storm holding sockets open is enough to walk the
# process into the OOM killer. Past this many the bus refuses outright rather
# than degrading for the people already watching; the dashboard reconnects with
# backoff, so a refusal is temporary from the client's side.
MAX_SUBSCRIBERS = 32


class SubscriberLimit(RuntimeError):
    """The bus is already carrying ``MAX_SUBSCRIBERS`` listeners."""


# A serialised ``WsEvent`` — what actually goes down the wire.
Frame = dict[str, Any]


class Subscription:
    def __init__(self, bus: "EventBus", maxsize: int = 1000) -> None:
        self._bus = bus
        self._queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=maxsize)

    def _put(self, frame: Frame) -> None:
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            # Drop the oldest event to keep the stream live rather than block producers.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(frame)

    async def __aiter__(self) -> AsyncIterator[Frame]:
        try:
            while True:
                yield await self._queue.get()
        finally:
            self._bus.unsubscribe(self)


class EventBus:
    def __init__(self, max_subscribers: int = MAX_SUBSCRIBERS) -> None:
        self._subs: set[Subscription] = set()
        self._max_subscribers = max_subscribers

    def subscribe(self) -> Subscription:
        """Attach a listener, or refuse if the bus is full.

        Raising rather than returning a dud subscription means a caller cannot
        forget to check: the websocket handler has to decide what to tell the
        client it is turning away.
        """
        if len(self._subs) >= self._max_subscribers:
            raise SubscriberLimit(
                f"{len(self._subs)} subscribers already attached (max {self._max_subscribers})"
            )
        sub = Subscription(self)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subs.discard(sub)

    def publish(self, event: WsEvent) -> None:
        subs = list(self._subs)
        if not subs:
            return
        # Serialise once for everybody, not once per listener. Every subscriber
        # receives byte-identical JSON, but the fan-out used to call
        # `model_dump(mode="json")` inside the loop — roughly sixteen dumps a
        # second per open dashboard at the simulator's tick rate, and a
        # `snapshot` frame walks the whole fleet, its latest telemetry and every
        # incident trace. The cost of running the feed scaled with the number of
        # people watching it, for no difference in what any of them saw.
        #
        # The frame is shared, not copied: nothing mutates it. Subscribers only
        # read it on the way into `websocket.send_json`.
        frame = event.model_dump(mode="json")
        for sub in subs:
            sub._put(frame)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    @property
    def max_subscribers(self) -> int:
        return self._max_subscribers


bus = EventBus()

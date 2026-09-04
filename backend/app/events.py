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

from .config import get_settings
from .models import WsEvent


class SubscriberLimit(RuntimeError):
    """The bus is already carrying as many listeners as it will hold."""


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
    def __init__(self, max_subscribers: int | None = None) -> None:
        # The cap is a deployment concern (see Settings.max_ws_subscribers for why it
        # exists and what it bounds), but it stays a constructor argument so a test can
        # build a bus of two without touching the environment.
        self._subs: set[Subscription] = set()
        self._max_subscribers = (
            get_settings().max_ws_subscribers if max_subscribers is None else max_subscribers
        )

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

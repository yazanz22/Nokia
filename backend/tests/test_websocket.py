"""The dashboard feed: /ws, the event bus behind it, and the request body cap.

These are the first tests in the suite to build the FastAPI app itself. They do it
without the lifespan — ``TestClient(app)`` outside a ``with`` block never runs
startup — which is deliberate: the simulator, the anomaly detector and the ML
warm-up would otherwise be publishing into the bus while these tests count
subscribers and frames. Everything here needs the routes and the socket, not a
running demo.
"""

from __future__ import annotations

import logging
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.events import EventBus, SubscriberLimit, bus
from app.main import app
from app.models import WsEvent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    """Poll a condition that is settled on the app's own thread.

    The websocket handler runs in the TestClient's portal thread, so a state change
    it makes is not visible the instant the client-side call returns.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _errors(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


# ── the socket ───────────────────────────────────────────────────────────────
def test_connect_gets_snapshot_and_disconnects_without_logging_an_error(client, caplog):
    caplog.set_level(logging.DEBUG)

    with client.websocket_connect("/ws") as sock:
        first = sock.receive_json()

    assert first["type"] == "snapshot"
    # The snapshot is what the dashboard renders from before any event arrives.
    assert {"assets", "technicians", "kpis", "dead_zones"} <= set(first["payload"])
    assert first["payload"]["assets"], "a fresh store seeds a demo fleet"

    # A normal disconnect is not an incident. This is the regression that matters:
    # the old handler let uvicorn's bare RuntimeError reach `log.exception`, so every
    # browser refresh printed a traceback and buried anything real.
    assert _errors(caplog) == []
    assert _wait_until(lambda: bus.subscriber_count == 0)


def test_client_going_away_is_noticed_without_waiting_for_a_publish(client):
    """A silent disconnect must free the subscription on its own.

    Nothing is publishing in this test — no lifespan, so no simulator ticking. If the
    handler only learned about the disconnect from a failed send, the subscription
    here would live forever. It is the pending `receive()` that ends it.
    """
    with client.websocket_connect("/ws") as sock:
        sock.receive_json()
        assert bus.subscriber_count == 1
        sock.close(1000)
        assert _wait_until(lambda: bus.subscriber_count == 0), (
            "subscription outlived the client on an idle bus"
        )


def test_published_events_reach_a_connected_client(client):
    with client.websocket_connect("/ws") as sock:
        sock.receive_json()  # snapshot
        assert _wait_until(lambda: bus.subscriber_count == 1)
        bus.publish(WsEvent(type="kpis", payload={"fleet_size": 7}))
        frame = sock.receive_json()

    assert frame["type"] == "kpis"
    assert frame["payload"]["fleet_size"] == 7


def test_client_chatter_is_discarded_rather_than_killing_the_socket(client, caplog):
    caplog.set_level(logging.DEBUG)

    with client.websocket_connect("/ws") as sock:
        sock.receive_json()  # snapshot
        sock.send_text("hello?")  # there is no inbound protocol
        bus.publish(WsEvent(type="kpis", payload={"fleet_size": 3}))
        assert sock.receive_json()["type"] == "kpis"

    assert _errors(caplog) == []


def test_socket_past_the_cap_is_refused_with_1013(client, caplog):
    caplog.set_level(logging.DEBUG)
    original = bus._max_subscribers
    bus._max_subscribers = 1
    try:
        with client.websocket_connect("/ws") as first:
            first.receive_json()
            with pytest.raises(WebSocketDisconnect) as refused:  # noqa: PT012
                with client.websocket_connect("/ws") as second:
                    second.receive_json()
        assert refused.value.code == 1013
    finally:
        bus._max_subscribers = original

    # Refusing a client is a warning, not an error, and it must not cost a snapshot.
    assert _errors(caplog) == []
    assert any("websocket refused" in r.getMessage() for r in caplog.records)
    assert _wait_until(lambda: bus.subscriber_count == 0)


# ── the bus ──────────────────────────────────────────────────────────────────
async def test_publish_serialises_once_for_every_subscriber(monkeypatch):
    real_dump = WsEvent.model_dump
    dumps: list[WsEvent] = []

    def counting_dump(self, *args, **kwargs):
        dumps.append(self)
        return real_dump(self, *args, **kwargs)

    monkeypatch.setattr(WsEvent, "model_dump", counting_dump)

    local = EventBus()
    subs = [local.subscribe() for _ in range(5)]
    local.publish(WsEvent(type="kpis", payload={"fleet_size": 30}))

    assert len(dumps) == 1, "one dump per event, not one per listener"
    frames = [s._queue.get_nowait() for s in subs]
    assert all(frame is frames[0] for frame in frames), "the same frame is fanned out"
    assert frames[0]["payload"] == {"fleet_size": 30}


async def test_publish_with_no_subscribers_serialises_nothing(monkeypatch):
    def explode(self, *args, **kwargs):
        raise AssertionError("serialised an event nobody is listening for")

    monkeypatch.setattr(WsEvent, "model_dump", explode)
    EventBus().publish(WsEvent(type="kpis", payload={}))


async def test_bus_refuses_past_its_cap():
    local = EventBus(max_subscribers=2)
    first, second = local.subscribe(), local.subscribe()
    with pytest.raises(SubscriberLimit):
        local.subscribe()

    # And makes room again as listeners leave.
    local.unsubscribe(first)
    third = local.subscribe()
    assert local.subscriber_count == 2
    assert third is not second


async def test_full_queue_drops_the_oldest_frame():
    local = EventBus()
    sub = local.subscribe()
    sub._queue = type(sub._queue)(maxsize=2)
    for n in range(4):
        local.publish(WsEvent(type="kpis", payload={"n": n}))
    kept = [sub._queue.get_nowait()["payload"]["n"] for _ in range(2)]
    assert kept == [2, 3], "a slow client loses history, never the live view"


# ── request body cap ─────────────────────────────────────────────────────────
def test_oversized_body_is_refused(client):
    from app.main import MAX_BODY_BYTES

    payload = {"pad": "x" * (MAX_BODY_BYTES + 1024)}
    response = client.post("/api/nac/geofence-callback", json=payload)
    assert response.status_code == 413
    assert "too large" in response.text or "exceeds" in response.text


def test_oversized_body_is_refused_without_a_content_length(client):
    from app.main import MAX_BODY_BYTES

    def chunks():
        sent = 0
        while sent <= MAX_BODY_BYTES + 4096:
            yield b"x" * 8192
            sent += 8192

    # A chunked request declares no length, so the header check alone would let this
    # through — the counting receive channel is what stops it.
    response = client.post("/api/nac/geofence-callback", content=chunks())
    assert response.status_code == 413


def test_a_normal_geofence_callback_still_gets_through(client):
    response = client.post(
        "/api/nac/geofence-callback",
        json={"eventType": "org.camaraproject.geofencing-subscriptions.v0.area-left"},
    )
    assert response.status_code == 200
    assert response.json() == {"received": True}


# ── docs ─────────────────────────────────────────────────────────────────────
def test_docs_are_served(client):
    # Deliberately on: a judge reads the CAMARA surface here. See the comment in
    # main.py for why, and for the DOCS_ENABLED switch that turns it off.
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200

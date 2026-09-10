"""FILO Asset Sentinel — FastAPI application.

Serves the REST API under ``/api`` and a single WebSocket at ``/ws`` that streams
telemetry, incidents, the agent reasoning trace, work orders and KPIs to the
operator dashboard.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketState

from .anomaly import detector
from .config import REPO_ROOT, get_settings
from .events import SubscriberLimit, bus
from .models import WsEvent
from .routes import api_router
from .simulator import simulator
from .store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info(
        "starting — NAC_MODE=%s AGENT_MODE=%s fleet=%d",
        settings.nac_mode,
        settings.agent_mode,
        len(store.assets),
    )
    simulator.start()
    detector.start()

    # Load the telemetry history and the feature module now, while nothing is watching.
    # The first fault prediction pays that cost otherwise, and it lands on the first
    # incident of the demo — a couple of seconds during which the simulator, the
    # detector and the websocket feed are all stopped. In a thread and unawaited so the
    # server is accepting requests immediately; wrapped because a missing model or CSV
    # is a slow first prediction, never a server that refuses to start.
    async def _warm_ml() -> None:
        try:
            from .ml.client import warm_up

            await asyncio.to_thread(warm_up)
        except Exception:  # noqa: BLE001
            log.warning("ML warm-up skipped", exc_info=True)

    warming = asyncio.create_task(_warm_ml())

    try:
        yield
    finally:
        warming.cancel()
        await detector.stop()
        await simulator.stop()
        # The live adapter holds an httpx client. Nothing was closing it, so every
        # reload leaked its connection pool.
        from .nac.factory import get_live_client

        live = get_live_client()
        closer = getattr(live, "aclose", None)
        if callable(closer):
            await closer()


# ── request body cap ─────────────────────────────────────────────────────────
# Nothing this app accepts is large. The biggest body is a CAMARA geofencing
# notification arriving at /api/nac/geofence-callback, which is a couple of
# kilobytes; a quarter of a megabyte is generous for every route here.
MAX_BODY_BYTES = 256 * 1024


class _BodyTooLarge(BaseException):
    """Internal signal from the counting receive channel back to the middleware.

    Derived from ``BaseException`` on purpose, and it is not an oversight. FastAPI
    parses the body inside ``try: ... except Exception: raise HTTPException(400,
    "There was an error parsing the body")``, so an ordinary exception raised from
    the receive channel is swallowed there and the caller gets a misleading 400
    instead of the 413 that says what actually happened. Nothing between here and
    the raise point catches ``BaseException``, so the signal reaches the one handler
    that knows what it means — the ``except`` below, which is the only place it is
    ever caught.
    """


class BodySizeLimit:
    """Refuse an oversized request body instead of buffering it.

    ``POST /api/nac/geofence-callback`` declares ``event: dict`` with no bound, and
    FastAPI reads the entire body into memory before the handler is ever entered.
    That URL is public by necessity — the operator has to be able to POST to it, and
    it is handed out as a subscription sink — so anybody who finds it can hand this
    512MB instance a multi-gigabyte body and watch the process die. A cap belongs
    here rather than on the one route, because the same is true of every other POST
    the app grows later.

    Enforced twice on purpose. The ``Content-Length`` check rejects before a single
    byte of body is read, which is the cheap path; but a chunked request carries no
    ``Content-Length`` at all, so a header-only limit is one an attacker opts out of
    by not declaring a length. Counting what actually arrives is what makes it real.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        seen = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def watching_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
        except _BodyTooLarge:
            # The body is read before the handler answers, so in practice nothing has
            # been sent yet. If somehow it has, there is no status line left to write
            # and the only honest thing is to let the error surface.
            if response_started:
                raise
            await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"detail": f"request body exceeds {self.max_bytes} bytes"}, status_code=413
        )
        await response(scope, receive, send)


_settings = get_settings()

# ── API documentation ────────────────────────────────────────────────────────
# /docs, /redoc and /openapi.json stay on by default, and DOCS_ENABLED=0 turns all
# three off together. See Settings.docs_enabled for why the default is on — briefly:
# the generated reference is how a judge inspects the CAMARA surface without reading
# the source, and the exposure is the unauthenticated routes themselves rather than
# their documentation.
app = FastAPI(
    title="FILO Asset Sentinel",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.docs_enabled else None,
    redoc_url="/redoc" if _settings.docs_enabled else None,
    openapi_url="/openapi.json" if _settings.docs_enabled else None,
)
# CORS exists only for local development, where Vite serves the dashboard on :5173
# and proxies to this API. A deployed build is served from this same origin, so no
# cross-origin access is needed and a wildcard would just let any site drive the demo.
if not (REPO_ROOT / "frontend" / "dist").is_dir():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{5173}",
            f"http://127.0.0.1:{5173}",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
# Added last so it wraps everything else: Starlette builds the stack outside-in from
# the most recently added middleware, and a body cap that runs after CORS has already
# buffered the request is not a cap.
app.add_middleware(BodySizeLimit)
app.include_router(api_router)


@app.get("/api/health")
def health() -> dict:
    # The cap is reported alongside the count so "the dashboard will not connect" is
    # diagnosable from one URL rather than from the logs of a deployed container.
    return {
        "status": "ok",
        "subscribers": bus.subscriber_count,
        "max_subscribers": bus.max_subscribers,
    }


# RFC 6455 / IANA close codes. 1013 "try again later" is what a server says when it
# is at capacity but the client is welcome back — which is exactly the situation, and
# the dashboard's reconnect backoff already does the coming back.
WS_TRY_AGAIN_LATER = 1013

# Once the peer is gone the send path raises whatever the server happens to raise
# there, and none of it has a distinct type. uvicorn raises a bare
# RuntimeError("Unexpected ASGI message 'websocket.send', after sending
# 'websocket.close'.") and Starlette raises RuntimeError('Cannot call "send" once a
# close message has been sent.'). The old handler caught Exception and logged it with
# a traceback, so an ordinary browser refresh printed a full stack at ERROR level —
# several times a minute during a demo, which is precisely how a real error becomes
# invisible. There is nothing to match on but the message.
_DISCONNECT_PHRASES = (
    "once a close message has been sent",
    "once a disconnect message has been received",
    "after sending 'websocket.close'",
    "websocket is not connected",
)


def _is_disconnect(exc: BaseException) -> bool:
    """True when this exception is the client leaving rather than a fault."""
    # OSError covers uvicorn's ClientDisconnected, which subclasses it, and the
    # ConnectionReset family underneath a dropped TCP connection.
    if isinstance(exc, (WebSocketDisconnect, OSError)):
        return True
    return isinstance(exc, RuntimeError) and any(
        phrase in str(exc).lower() for phrase in _DISCONNECT_PHRASES
    )


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        sub = bus.subscribe()
    except SubscriberLimit as exc:
        # Turn the client away explicitly rather than accepting a socket we are not
        # prepared to feed. Refusing before the snapshot is the point: building one
        # costs a walk of the whole fleet, and an unbounded public URL means an
        # unbounded number of those.
        log.warning("websocket refused: %s", exc)
        # A client that has already given up on the handshake must not turn a refusal
        # into a logged traceback of its own.
        with contextlib.suppress(Exception):
            await websocket.close(code=WS_TRY_AGAIN_LATER, reason="dashboard limit reached")
        return

    async def _pump() -> None:
        # Prime the new client with the full current state, then follow the bus. The
        # frames arrive already serialised — see EventBus.publish.
        await websocket.send_json(
            WsEvent(type="snapshot", payload=store.snapshot()).model_dump(mode="json")
        )
        async for frame in sub:
            await websocket.send_json(frame)

    async def _drain() -> None:
        """Watch the receive side so a client that vanishes is noticed at once.

        The dashboard never sends us anything, so this loop exists for its side
        effect. With no pending receive() a disconnect is only discovered when some
        later send happens to fail, so a tab closed on a quiet fleet kept its
        subscription — and its 1000-slot queue — alive until the next publish fell
        over it. Anything the client does send is discarded; there is no inbound
        protocol.
        """
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    pump = asyncio.create_task(_pump())
    drain = asyncio.create_task(_drain())
    try:
        # Whichever side finishes first ends the session: the reader sees the client
        # go, or the writer fails trying to reach it.
        done, _ = await asyncio.wait({pump, drain}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not _is_disconnect(exc):
                log.error("websocket error", exc_info=exc)
    finally:
        for task in (pump, drain):
            task.cancel()
        for task in (pump, drain):
            # Already logged above if it mattered; here we only need the tasks to be
            # finished before the handler returns.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        # Cancelling _pump mid-iteration unsubscribes through the generator's own
        # finally; this covers the paths that never reached the loop.
        bus.unsubscribe(sub)
        if websocket.application_state is WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()


# ── static dashboard ─────────────────────────────────────────────────────────
# In development the dashboard is served by Vite on :5173 and proxies /api here.
# For a deployed single-service demo we serve the built bundle ourselves, so the
# whole thing is one container behind one URL.
# Python resolves MIME types from the Windows registry, where .js is routinely
# registered as text/plain. Browsers refuse to execute an ES module served with the
# wrong type, so the bundle downloads and is silently ignored — a blank page with no
# error. Pin the types we serve rather than trusting the host.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/png", ".png")

_DIST = REPO_ROOT / "frontend" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    # Everything Vite copies from public/ lands in the dist ROOT, not in assets/ —
    # the favicons and the brand mark. Only /assets was mounted, so under the
    # single-service build (the one that deploys) every one of them 404'd and the
    # header rendered a broken-image glyph. Enumerated once at startup rather than
    # joining a URL segment onto a directory per request, which is a path traversal
    # waiting to be written; nothing here is dynamic, so there is nothing to gain
    # from resolving it late. The single-segment path parameter cannot match a
    # slash, and /api, /ws and /assets are all registered above this, so it sees
    # only what they have already declined.
    _ROOT_FILES = {
        f.name: f for f in _DIST.iterdir() if f.is_file() and f.name != "index.html"
    }

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:
        return FileResponse(_DIST / "index.html")

    @app.get("/{filename}", include_in_schema=False)
    def _root_file(filename: str) -> FileResponse:
        path = _ROOT_FILES.get(filename)
        if path is None:
            raise HTTPException(404, "not found")
        return FileResponse(path)

    log.info("serving dashboard from %s", _DIST)
else:
    log.info("no frontend build at %s — run `npm run build` for single-service mode", _DIST)


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
    )


if __name__ == "__main__":
    run()

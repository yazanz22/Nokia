"""FILO Asset Sentinel — FastAPI application.

Serves the REST API under ``/api`` and a single WebSocket at ``/ws`` that streams
telemetry, incidents, the agent reasoning trace, work orders and KPIs to the
operator dashboard.
"""

from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .anomaly import detector
from .config import REPO_ROOT, get_settings
from .events import bus
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
    try:
        yield
    finally:
        await detector.stop()
        await simulator.stop()
        # The live adapter holds an httpx client. Nothing was closing it, so every
        # reload leaked its connection pool.
        from .nac.factory import get_live_client

        live = get_live_client()
        closer = getattr(live, "aclose", None)
        if callable(closer):
            await closer()


app = FastAPI(title="FILO Asset Sentinel", version="0.1.0", lifespan=lifespan)
# CORS exists only for local development, where Vite serves the dashboard on :5173
# and proxies to this API. A deployed build is served from this same origin, so no
# cross-origin access is needed and a wildcard would just let any site drive the demo.
_settings = get_settings()
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
app.include_router(api_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "subscribers": bus.subscriber_count}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    sub = bus.subscribe()
    # Prime the new client with the full current state.
    await websocket.send_json(WsEvent(type="snapshot", payload=store.snapshot()).model_dump(mode="json"))
    try:
        async for event in sub:
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("websocket error")
    finally:
        bus.unsubscribe(sub)


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

_DIST = REPO_ROOT / "frontend" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:
        return FileResponse(_DIST / "index.html")

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

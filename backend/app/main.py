"""FILO Asset Sentinel — FastAPI application.

Serves the REST API under ``/api`` and a single WebSocket at ``/ws`` that streams
telemetry, incidents, the agent reasoning trace, work orders and KPIs to the
operator dashboard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .anomaly import detector
from .config import get_settings
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


app = FastAPI(title="FILO Asset Sentinel", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

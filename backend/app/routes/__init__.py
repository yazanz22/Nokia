from fastapi import APIRouter

from . import assets, debug, incidents, scenarios, workorders

api_router = APIRouter(prefix="/api")
api_router.include_router(assets.router)
api_router.include_router(incidents.router)
api_router.include_router(workorders.router)
api_router.include_router(scenarios.router)
api_router.include_router(debug.router)

__all__ = ["api_router"]

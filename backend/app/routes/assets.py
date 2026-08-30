from fastapi import APIRouter, HTTPException

from ..store import store

router = APIRouter(tags=["assets"])


@router.get("/assets")
def list_assets() -> dict:
    return {
        "assets": [a.model_dump(mode="json") for a in store.assets.values()],
        "technicians": [t.model_dump(mode="json") for t in store.technicians.values()],
    }


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    asset = store.assets.get(asset_id)
    if asset is None:
        raise HTTPException(404, f"unknown asset {asset_id}")
    sample = store.latest_telemetry.get(asset_id)
    return {
        "asset": asset.model_dump(mode="json"),
        "latest_telemetry": sample.model_dump(mode="json") if sample else None,
    }

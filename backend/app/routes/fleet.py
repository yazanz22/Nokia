from fastapi import APIRouter

from ..ml.forecast import forecast_model
from ..store import store

router = APIRouter(tags=["fleet"])


@router.get("/fleet/health")
def fleet_health() -> dict:
    """Predictive maintenance view: which machines are trending toward failure.

    Nothing here has broken yet — this is the proactive half of the system, the
    counterpart to the reactive incident flow.
    """
    if not forecast_model.available:
        return {"available": False, "assets": [], "at_risk": 0}

    scored = forecast_model.score_fleet(list(store.assets))
    for row in scored:
        asset = store.assets.get(row["asset_id"])
        if asset:
            row["label"] = asset.label
            row["site"] = asset.site
    return {
        "available": True,
        "as_of": scored[0]["as_of"] if scored else None,
        "at_risk": sum(1 for s in scored if s["at_risk"]),
        "fleet_size": len(scored),
        "assets": scored,
    }

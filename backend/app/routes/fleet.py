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

    # Only machines that are still in service get scored. A forecast is a claim about
    # a machine that is running now and will not be later; once an asset has gone
    # silent, been confirmed a blindspot, or had a technician dispatched to it, that
    # claim is already settled and the row is no longer a prediction. During the demo
    # this was literal: the excavator the agent had just diagnosed and dispatched
    # reappeared as a sixth row in the predictive panel, ringed on the map, while the
    # narration said the panel holds machines that have not failed. "healthy" and
    # "anomaly" are the two states where the machine is still reporting and no
    # incident is open against it — everything else belongs to the reactive half.
    in_service = [aid for aid, a in store.assets.items() if a.state in ("healthy", "anomaly")]
    scored = forecast_model.score_fleet(in_service)
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

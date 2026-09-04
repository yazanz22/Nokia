from fastapi import APIRouter, HTTPException

from ..store import store

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
def list_incidents() -> dict:
    return {
        "incidents": [
            i.model_dump(mode="json")
            for i in sorted(store.incidents.values(), key=lambda x: x.opened_at, reverse=True)
        ]
    }


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    inc = store.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, f"unknown incident {incident_id}")
    return {
        "incident": inc.model_dump(mode="json"),
        "trace": [s.model_dump(mode="json") for s in store.trace.get(incident_id, [])],
        "work_orders": [
            w.model_dump(mode="json")
            for w in store.work_orders.values()
            if w.incident_id == incident_id
        ],
    }


@router.get("/geofence-alerts")
def list_geofence_alerts() -> dict:
    """Perimeter crossings — machines that left the site while still healthy.

    Separate from /incidents on purpose. An incident is something that already went
    wrong; these are the ones that did not.
    """
    return {
        "geofence_alerts": [
            a.model_dump(mode="json")
            for a in sorted(store.geofence_alerts.values(), key=lambda a: a.at, reverse=True)
        ],
        "incidents_prevented": store.incidents_prevented,
    }

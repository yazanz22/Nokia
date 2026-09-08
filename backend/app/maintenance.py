"""Scheduled maintenance — the two halves of the work that is *not* a breakdown.

Fleets divide maintenance three ways, and the split is about what triggered the work
rather than what gets done to the machine:

* **corrective** — it already broke. Unplanned, urgent, and the expensive one. That is
  the incident path: ``anomaly/detector.py`` opens an incident, the agent rules the
  network in or out, and ``agent/tools.py::create_work_order`` raises the job.
* **preventive** — nothing is wrong; the service interval came due. Driven by a clock
  and an hour meter, known days in advance, and the cheapest of the three.
* **predictive** — nothing has failed *yet*, but the forecast model expects it to. The
  trigger is a condition signal rather than a calendar.

This module owns the second and third. The first stays where it is, because it starts
from an incident and these two never have one.

The reason all three live in one vocabulary rather than being three unrelated screens:
a machine that is *both* due a service and forecast to fail is one visit, not two. That
is what ``bundle_candidates`` finds, and it is the only place in the system where the
service clock and the forecast model meet.
"""

from __future__ import annotations

from typing import Any

from .ml.forecast import forecast_model
from .models import Asset
from .seed import COMPONENT_PARTS, SERVICE_KIT_PART
from .store import store

# How far ahead of the interval a machine starts appearing on the board. Far enough to
# plan a visit around, short enough that the list is not the whole fleet — at 500-hour
# intervals on machines running roughly a shift a day, 50 hours is about a fortnight's
# notice.
DUE_SOON_HOURS = 50.0


def service_state(asset: Asset) -> str:
    """``overdue`` | ``due_soon`` | ``ok`` for one machine's service clock."""
    if asset.service_overdue:
        return "overdue"
    if asset.service_due_in_hours <= DUE_SOON_HOURS:
        return "due_soon"
    return "ok"


def _row(asset: Asset) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "label": asset.label,
        "site": asset.site,
        "engine_hours": round(asset.engine_hours, 1),
        "service_interval_hours": asset.service_interval_hours,
        "hours_since_service": round(asset.hours_since_service, 1),
        "due_in_hours": round(asset.service_due_in_hours, 1),
        "state": service_state(asset),
        "part": SERVICE_KIT_PART,
    }


def service_board(include_ok: bool = False) -> list[dict[str, Any]]:
    """Every machine's service position, most overdue first.

    Machines already out of service are still listed. A machine with a technician
    driving to it is exactly the machine you want to notice is also 30 hours past its
    service — that is the cheapest possible moment to do both, and dropping it from the
    board is how a fleet ends up making the second trip a week later.
    """
    rows = [_row(a) for a in store.assets.values()]
    if not include_ok:
        rows = [r for r in rows if r["state"] != "ok"]
    rows.sort(key=lambda r: r["due_in_hours"])
    return rows


def scheduled_for(asset_id: str) -> bool:
    """Is there already an open scheduled job on this machine?

    Preventive and predictive work is raised by an operator pressing a button, and a
    button can be pressed twice. One machine, one open scheduled visit.
    """
    return any(
        w.asset_id == asset_id
        and w.maintenance_type in ("preventive", "predictive")
        and w.status != "completed"
        for w in store.work_orders.values()
    )


def bundle_candidates(risk_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Machines where a forecast failure and a due service land on the same visit.

    The saving here is a whole journey. Both jobs need a technician at the same machine
    with a part from the same depot, and doing them together costs one mobilisation,
    one drive and one loading stop instead of two of each — on a site where the depot
    leg alone ran to 53 km in testing, that is not a rounding error.

    Deliberately a *recommendation* rather than something the system does on its own.
    Bundling changes what a technician is sent to do, and there are real reasons an
    operator might refuse: a machine forecast to fail in under a day should be repaired
    now and serviced later, not held up while somebody loads a service kit. So this
    reports the opportunity and the operator decides, which is the same division of
    labour the agent has with dispatch — it decides *whether*, never *what*.
    """
    by_id = {r["asset_id"]: r for r in risk_rows if r.get("at_risk")}
    out: list[dict[str, Any]] = []
    for asset in store.assets.values():
        risk = by_id.get(asset.id)
        if risk is None or service_state(asset) == "ok":
            continue
        # The forecast says a failure is coming; it does not say what fails. That is a
        # second model, and it is asked here rather than in the fleet scorer because
        # only these few machines need the answer — running it across the fleet to
        # populate a column almost nobody reads is how the predictive panel became slow
        # the first time.
        identified = forecast_model.identify_component(asset.id)
        if identified is None:
            # No opinion — most often a workshop repair gap inside the trailing window.
            # A bundle needs a named part to collect, so there is nothing to offer.
            continue
        component, component_confidence = identified
        part = COMPONENT_PARTS.get(component, ("", 0))[0]
        # Only offer the bundle if one depot can supply both items. Two depots is a
        # third leg, at which point the bundle costs more than it saves and the two
        # jobs are genuinely better done separately.
        wanted = [p for p in (part, SERVICE_KIT_PART) if p]
        if not wanted or not store.depots_stocking(wanted):
            continue
        out.append(
            {
                **_row(asset),
                "component": component,
                "component_confidence": round(component_confidence, 3),
                "component_part": part,
                "depot": store.depots_stocking(wanted)[0],
                "horizon_hours": risk.get("horizon_hours"),
                "risk": risk.get("risk"),
                "already_scheduled": scheduled_for(asset.id),
            }
        )
    out.sort(key=lambda r: (r["horizon_hours"] or 999, r["due_in_hours"]))
    return out

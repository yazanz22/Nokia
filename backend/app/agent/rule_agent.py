"""Deterministic closed-loop investigation.

This is the reference behaviour the LLM agent must reproduce. No model call — it
always completes, which makes it the on-stage failsafe (``AGENT_MODE=rule``).

    silent heartbeat
      -> CAMARA Device Status
        -> coverage gap  : notify + schedule re-check, NO dispatch
        -> network fine  : ML fault prediction
                           -> CAMARA Location Retrieval
                           -> work order + nearest technician
"""

from __future__ import annotations

import logging

from ..models import utcnow
from ..store import store
from .tools import (
    assess_coverage_gap,
    check_device_status,
    create_work_order,
    get_device_location,
    predict_fault,
    schedule_recheck,
)
from .trace import Tracer

log = logging.getLogger("agent.rule")


async def run_rule_investigation(incident_id: str) -> None:
    inc = store.incidents[incident_id]
    asset_id = inc.asset_id
    asset = store.assets[asset_id]
    t = Tracer(incident_id)

    inc.status = "investigating"
    store.update_incident(inc)

    await t.step(
        f"{asset.label} ({asset_id}) stopped transmitting. Before rolling a truck I need to know "
        f"whether the network dropped it or the machine did. Querying CAMARA Device Status.",
    )

    reach = await check_device_status(asset_id)
    await t.step(
        "Read network-verified device status.",
        tool="camara.device_status",
        args={"asset_id": asset_id},
        observation=(
            f"status={reach.status}, signal={reach.signal_strength_dbm} dBm, "
            f"neighbour_failures={reach.neighbor_fail_count}, source={reach.source}"
        ),
    )

    is_gap, why = assess_coverage_gap(reach)
    await t.step(f"Interpreting the network signal. {why}")

    if is_gap:
        recheck_at = schedule_recheck(asset_id, minutes=15)
        await t.step(
            "Logged a cellular blind spot. Scheduling an automated re-check and notifying the "
            "operator — no field dispatch.",
            tool="ops.schedule_recheck",
            args={"asset_id": asset_id, "at": recheck_at.isoformat()},
            observation="re-check queued; operator notified",
        )
        store.set_asset_state(asset_id, "blindspot")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="network_blindspot",
            resolution=(
                f"Cellular blind spot confirmed via CAMARA Device Status ({reach.status}, "
                f"{reach.signal_strength_dbm:.0f} dBm). Re-check at {recheck_at:%H:%M UTC}. "
                "No technician dispatched — false dispatch avoided."
            ),
        )
        store.publish_kpis()
        log.info("%s resolved as blindspot", incident_id)
        return

    # ── network is fine (or unreachable-but-strong-signal) -> hardware path ──
    await t.step(
        "Network checks out, so the silence is the equipment. Running the ML fault model on the "
        "last telemetry frame before the uplink dropped.",
    )
    fault = predict_fault(asset_id, reach)
    await t.step(
        "ML fault classification complete.",
        tool="ml.predict_fault",
        args={"asset_id": asset_id, "model": "fault-classifier"},
        observation=(
            f"{fault.mode} @ {fault.confidence:.0%} (part: {fault.recommended_part or 'n/a'}). "
            f"{fault.rationale}"
        ),
    )

    # A dispatch is only justified if the model actually found a fault. Rolling a
    # truck to a machine that reads healthy is the same wasted journey as rolling one
    # into a coverage gap — the cause differs, the cost does not.
    if fault.mode == "NORMAL":
        recheck_at = schedule_recheck(asset_id, minutes=15)
        await t.step(
            "The model finds nothing wrong — every channel is within its nominal band. This reads "
            "as a transient dropout, not a breakdown. Scheduling a re-check rather than sending "
            "anyone.",
            tool="ops.schedule_recheck",
            args={"asset_id": asset_id, "at": recheck_at.isoformat()},
            observation="re-check queued; operator notified; no dispatch",
        )
        store.set_asset_state(asset_id, "healthy")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="no_fault",
            resolution=(
                f"No fault found. Network reachable and telemetry nominal at "
                f"{fault.confidence:.0%} confidence — treated as a transient dropout. "
                f"Re-check at {recheck_at:%H:%M UTC}. No technician dispatched."
            ),
        )
        store.publish_kpis()
        log.info("%s resolved as no_fault", incident_id)
        return

    loc = await get_device_location(asset_id)
    await t.step(
        "Pulled network-verified coordinates for dispatch (on-board GPS is dark).",
        tool="camara.location_retrieval",
        args={"asset_id": asset_id},
        observation=(
            f"lat={loc.latitude:.5f}, lon={loc.longitude:.5f}, ±{loc.accuracy_m:.0f} m, "
            f"source={loc.source}"
        ),
    )

    wo = create_work_order(incident_id, asset_id, fault, loc)
    await t.step(
        "Generated work order and assigned the nearest qualified technician.",
        tool="ops.create_work_order",
        args={"incident_id": incident_id, "asset_id": asset_id, "part": wo.part},
        observation=(
            f"{wo.id} -> {wo.technician_name or 'unassigned'} "
            f"({wo.distance_km:.1f} km, ETA {wo.eta_minutes} min) carrying {wo.part or 'n/a'}"
        ),
    )

    store.set_asset_state(asset_id, "dispatched")
    store.close_incident(
        inc,
        status="hardware_confirmed",
        resolution=(
            f"Hardware fault confirmed: {fault.mode} @ {fault.confidence:.0%}. "
            f"{wo.id} dispatched to {wo.technician_name} (ETA {wo.eta_minutes} min) with {wo.part}. "
            f"Diagnosed and dispatched in {(utcnow() - inc.opened_at).total_seconds():.0f}s."
        ),
    )
    store.publish_kpis()
    log.info("%s resolved as hardware_confirmed -> %s", incident_id, wo.id)

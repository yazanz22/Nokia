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
    assess_silence,
    check_device_status,
    create_work_order,
    get_device_location,
    predict_fault,
    schedule_recheck,
)
from .memory import memory
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

    # What have we learned about this machine and this patch of ground before?
    past = memory.recall(asset_id, asset.latitude, asset.longitude)
    if past.has_history:
        await t.step(
            f"Checking what we already know. {past.summary}",
            tool="memory.recall",
            args={"asset_id": asset_id},
            observation=(
                f"asset incidents={past.asset_seen}, incidents in this area={past.cell_seen}, "
                f"known dead zone={past.known_dead_zone}"
            ),
        )

    reach = await check_device_status(asset_id)
    await t.step(
        "Read network-verified device status.",
        tool="camara.device_status",
        args={"asset_id": asset_id},
        observation=(
            f"status={reach.status}, signal={reach.signal_strength_dbm} dBm, "
            f"neighbour_failures={reach.neighbor_fail_count}, "
            f"area_congestion={reach.congestion_level or 'n/a'}"
            + (f" @ {reach.congestion_confidence}%" if reach.congestion_confidence is not None else "")
            + f", source={reach.source}"
        ),
    )

    verdict = assess_silence(reach)
    await t.step(f"Interpreting the network signal. {verdict.explanation}")

    if verdict.category == "roaming_out":
        # Only the roaming API surfaces this. The machine is healthy and attached —
        # to somebody else's network — so the fix is a connectivity ticket, and
        # sending a mechanic would be as wasted a trip as chasing a coverage gap.
        recheck_at = schedule_recheck(asset_id, minutes=30)
        await t.step(
            "Raising a connectivity ticket, not a field job. Nobody is dispatched.",
            tool="ops.notify_operator",
            args={"asset_id": asset_id, "queue": "connectivity", "at": recheck_at.isoformat()},
            observation=f"roaming on {reach.country}; APN unreachable from that network",
        )
        store.set_asset_state(asset_id, "blindspot")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="roaming_blocked",
            resolution=(
                f"Device roamed onto a {reach.country} network at the site boundary and its "
                f"telemetry APN no longer reaches us. Machine is healthy and attached. "
                f"Connectivity ticket raised, re-check at {recheck_at:%H:%M UTC}. "
                "No technician dispatched — false dispatch avoided."
            ),
        )
        memory.record(asset_id, asset.latitude, asset.longitude, "roaming_blocked")
        store.publish_kpis()
        log.info("%s resolved as roaming_blocked", incident_id)
        return

    if verdict.category == "coverage_gap":
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
        memory.record(asset_id, asset.latitude, asset.longitude, "network_blindspot")
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
            f"{fault.mode} @ {fault.confidence:.0%}"
            + (f", component: {fault.component.replace('_', ' ')} "
               f"@ {fault.component_confidence:.0%}" if fault.component else "")
            + f" (part: {fault.recommended_part or 'n/a'}). {fault.rationale}"
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
        # Judged healthy, so the heartbeat has to come back — otherwise the detector
        # re-opens this same incident in thirty seconds and we investigate forever.
        store.resume_telemetry(asset_id)
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
        memory.record(asset_id, asset.latitude, asset.longitude, "no_fault")
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

    await t.step(
        "Now I need the nearest technician who is actually carrying the part. Crews move "
        "between jobs, so I locate them the same way I located the machine — their phones "
        "are on the same network.",
        tool="camara.location_retrieval",
        args={"subject": "available crew"},
        observation="crew positions refreshed from the network",
    )

    wo = await create_work_order(incident_id, asset_id, fault, loc)
    await t.step(
        "Generated work order and assigned the nearest technician who is actually carrying "
        "the part. Closest is not the same as soonest fixed.",
        tool="ops.create_work_order",
        args={"incident_id": incident_id, "asset_id": asset_id, "part": wo.part},
        observation=(
            f"{wo.id} -> {wo.technician_name or 'unassigned'} "
            f"({wo.distance_km:.1f} km, ETA {wo.eta_minutes} min) carrying {wo.part or 'n/a'}; "
            f"crew position source={wo.technician_located_via}"
            + (
                f". {wo.nearest_skipped_name} is nearer at {wo.nearest_skipped_km:.1f} km but is "
                f"not carrying a {wo.part} — a closer technician who cannot fix it is a second trip."
                if wo.nearest_skipped_name
                else ""
            )
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
    memory.record(asset_id, asset.latitude, asset.longitude, "hardware_confirmed")
    store.publish_kpis()
    log.info("%s resolved as hardware_confirmed -> %s", incident_id, wo.id)

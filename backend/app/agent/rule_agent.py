"""Deterministic closed-loop investigation.

This is the reference behaviour the LLM agent must reproduce. No model call — it
always completes, which makes it the on-stage failsafe (``AGENT_MODE=rule``).

    silent heartbeat
      -> CAMARA Device Status + Roaming + Congestion Insights
        -> roaming abroad : connectivity ticket, NO dispatch
        -> coverage gap   : notify + schedule re-check, NO dispatch
        -> network fine   : ML fault prediction
             -> NETWORK_OUTAGE : the model blames the network too, NO dispatch
             -> NORMAL         : transient dropout, resume telemetry, NO dispatch
             -> a real fault   : CAMARA Location Retrieval (asset, then crew)
                                 -> work order + nearest technician carrying the part
                                 -> nobody free : job queued unassigned, NO dispatch claimed

Six outcomes. Three send nobody; a sensor fault sends a cheap kit; a hardware fault
sends a mechanic with the component the machine's own history points at; and a fully
booked crew queues the job honestly instead of writing a dispatch with no one on it.
"""

from __future__ import annotations

import asyncio
import logging

from ..ml.client import _pct
from ..models import utcnow
from ..store import store
from .tools import (
    assess_silence,
    check_device_status,
    create_work_order,
    get_device_location,
    park_awaiting_crew,
    predict_fault,
    queued_observation,
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
        # CAMARA Device Status returns attachment and nothing about the radio, so
        # against a real operator this field is None — and Congestion Insights is
        # exactly what makes a coverage gap reachable without it. Formatting None
        # raised a TypeError that the detector swallowed, leaving the incident stuck
        # at "investigating" with a half-written trace and nobody ever sent.
        sig = reach.signal_strength_dbm
        evidence = (
            f"{sig:.0f} dBm"
            if sig is not None
            else f"area congestion {reach.congestion_level or 'unavailable'}"
        )
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
                f"{evidence}). Re-check at {recheck_at:%H:%M UTC}. "
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
    # Off the event loop. The classifier is scikit-learn, and its first call also drags
    # in the feature module and parses 33k rows of telemetry history — ~2s of pure CPU
    # the first time it runs. Called inline it freezes the simulator tick, the anomaly
    # detector and every websocket send with it: the dashboard stops dead mid-incident,
    # on stage, at exactly the moment the audience is watching the agent think.
    fault = await asyncio.to_thread(predict_fault, asset_id, reach)
    await t.step(
        "ML fault classification complete.",
        tool="ml.predict_fault",
        args={"asset_id": asset_id, "model": "fault-classifier"},
        observation=(
            f"{fault.mode} @ {fault.confidence:.0%}"
            + (f", component: {fault.component.replace('_', ' ')} "
               f"@ {_pct(fault.component_confidence)}" if fault.component else "")
            + f" (part: {fault.recommended_part or 'n/a'}). {fault.rationale}"
        ),
    )

    # There is no part for a coverage gap. The verdict branch above catches the clear
    # cases, but the classifier reads the radio channels itself and can call an outage
    # the assessment scored as ambiguous — and PARTS_CATALOGUE["NETWORK_OUTAGE"] is
    # empty, so create_work_order would drop the part filter and send someone with
    # nothing. Both agents refuse it, for the same reason.
    if fault.mode == "NETWORK_OUTAGE":
        recheck_at = schedule_recheck(asset_id, minutes=15)
        await t.step(
            "The classifier attributes the silence to the network rather than the machine, "
            "and there is no part to carry to a coverage gap. Scheduling a re-check.",
            tool="ops.schedule_recheck",
            args={"asset_id": asset_id, "at": recheck_at.isoformat()},
            observation="re-check queued; operator notified; no dispatch",
        )
        store.set_asset_state(asset_id, "blindspot")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="network_blindspot",
            resolution=(
                f"Cellular blind spot: the fault model attributes the silence to the network "
                f"at {fault.confidence:.0%} confidence. Re-check at {recheck_at:%H:%M UTC}. "
                "No technician dispatched — false dispatch avoided."
            ),
        )
        memory.record(asset_id, asset.latitude, asset.longitude, "network_blindspot")
        store.publish_kpis()
        log.info("%s resolved as blindspot (model)", incident_id)
        return

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

    # Nobody free. Say that, rather than writing a dispatch with an empty name on it.
    # Same branch, same helper, same words as the LLM agent — the two agents disagreeing
    # about how an outcome is recorded is the recurring bug in this codebase.
    if wo.technician_id is None:
        await t.step(
            "The job is ready but every technician on the crew is already out on one. I am not "
            "going to record a dispatch that is not happening: the work order is queued "
            "unassigned, and the machine stays on the sweep so it is picked up the moment "
            "somebody frees.",
            tool="ops.create_work_order",
            args={
                "incident_id": incident_id,
                "asset_id": asset_id,
                "part": wo.part,
                "status": "queued",
            },
            observation=queued_observation(wo),
        )
        park_awaiting_crew(incident_id, asset_id, wo, fault)
        log.info("%s queued %s — no technician free", incident_id, wo.id)
        return

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
    # Both of these send somebody, and that is where the resemblance ends. A failed
    # reporting sensor leaves a working machine that cannot describe itself — a cheap
    # kit and a technician. A device failure is the machine itself, and costs a mechanic
    # and the component the history named. Closing them under one status made the
    # cheaper of the two outcomes unreadable in the record and on the dashboard.
    elapsed = (utcnow() - inc.opened_at).total_seconds()
    if fault.mode == "SENSOR_FAILURE":
        status = "sensor_confirmed"
        resolution = (
            f"Reporting sensor failed, not the machine: {fault.mode} @ {fault.confidence:.0%} — "
            f"every physical channel reads nominal. No mechanic needed. {wo.id} sends "
            f"{wo.technician_name} (ETA {wo.eta_minutes} min) with a {wo.part} to replace the "
            f"telemetry sensor. Diagnosed and dispatched in {elapsed:.0f}s."
        )
    else:
        status = "hardware_confirmed"
        resolution = (
            f"Hardware fault confirmed: {fault.mode} @ {fault.confidence:.0%}. "
            f"{wo.id} dispatched to {wo.technician_name} (ETA {wo.eta_minutes} min) with {wo.part}. "
            f"Diagnosed and dispatched in {elapsed:.0f}s."
        )
    store.close_incident(inc, status=status, resolution=resolution)
    memory.record(asset_id, asset.latitude, asset.longitude, status)
    store.publish_kpis()
    log.info("%s resolved as %s -> %s", incident_id, status, wo.id)

"""Pydantic AI agent (Resource & Tooling Guide §2) driving an open-weights model on
Groq (§3) — see LLM_MODEL. The CAMARA APIs and the ML models are registered as tools
the model chooses to call (§11); this is not a fixed script.

Same actions, same guardrails as ``rule_agent``: the model must finish by calling
exactly one terminal tool (``resolve_as_blindspot`` or ``dispatch_technician``).
If it doesn't, ``run_investigation`` falls back to the rule agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

# Imported at module scope, not inside the builder: this module uses
# `from __future__ import annotations`, so Pydantic AI resolves each tool's
# `ctx: RunContext[Deps]` annotation from module globals when the decorator runs.
# A function-local import leaves it undefined and every tool registration fails.
# The cost is nil — this module is itself only imported when AGENT_MODE=llm.
from pydantic_ai import Agent, RunContext

from ..config import get_settings
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

log = logging.getLogger("agent.llm")

SYSTEM_PROMPT = """\
You are the autonomous diagnostic agent for a heavy-equipment fleet on a MENA giga-project
(NEOM-scale sites, thousands of km2, patchy cellular coverage).

An asset has stopped sending telemetry. Your job: decide, WITHOUT a human, whether this is a
cellular coverage gap (do NOT send anyone) or a real hardware fault (dispatch a technician with
the right part). A wasted desert dispatch costs fuel, labour and crew safety margin; a missed
breakdown costs far more.

Policy:
0. Call `recall_history` first — if this patch of the site is a known dead zone, a
   coverage verdict needs less corroboration than it would on fresh ground.
1. Then call `check_device_status`. `NOT_CONNECTED` is ambiguous on its own.
2. Use `assess_coverage` to weigh serving-cell signal and neighbour-cell failures:
   - weak signal AND neighbour failures  -> coverage gap.
   - unreachable BUT strong signal, no neighbour failures -> the network is fine; the machine died.
   - reachable BUT roaming on a foreign network -> the machine is fine, its telemetry just
     cannot reach us from that operator. This is a connectivity ticket, never a mechanic.
3. Coverage gap -> call `resolve_as_blindspot`. Do not predict faults, do not dispatch.
4. Foreign roaming -> call `resolve_as_roaming`. Do not predict faults, do not dispatch.
5. Otherwise -> call `predict_fault`, then `get_location`, then `dispatch_technician`.

You MUST finish by actually invoking exactly one of `resolve_as_blindspot`,
`resolve_as_roaming` or `dispatch_technician` as a real tool call. Writing out the tool name and its arguments as
text — JSON or prose — does nothing: the incident stays open and no one is dispatched.
Nothing happens until the tool is invoked.

Keep reasoning short and concrete.
"""


@dataclass
class Deps:
    incident_id: str
    asset_id: str
    tracer: Tracer
    terminal: str | None = None
    last_fault: object = None
    verdict: object = None
    _reach: object = None


def _remember(asset_id: str, category: str) -> None:
    asset = store.assets.get(asset_id)
    if asset is not None:
        memory.record(asset_id, asset.latitude, asset.longitude, category)


def _build_agent():
    settings = get_settings()
    agent = Agent(settings.llm_model, deps_type=Deps, system_prompt=SYSTEM_PROMPT, retries=2)

    @agent.tool
    async def recall_history(ctx: RunContext[Deps]) -> str:
        """What has happened to this machine, and in this part of the site, before?
        Call this first — a known dead zone changes how much evidence you need."""
        d = ctx.deps
        asset = store.assets.get(d.asset_id)
        if asset is None:
            return "no history"
        past = memory.recall(d.asset_id, asset.latitude, asset.longitude)
        if past.has_history:
            await d.tracer.step(
                f"Checking what we already know. {past.summary}",
                tool="memory.recall",
                args={"asset_id": d.asset_id},
                observation=(
                    f"asset incidents={past.asset_seen}, incidents in this area={past.cell_seen}, "
                    f"known dead zone={past.known_dead_zone}"
                ),
            )
        return (
            f"prior_incidents_this_asset={past.asset_seen} "
            f"prior_incidents_this_area={past.cell_seen} "
            f"known_dead_zone={past.known_dead_zone}. {past.summary}"
        )

    @agent.tool
    async def check_device_status_tool(ctx: RunContext[Deps]) -> str:
        """CAMARA Device Status: is the SIM attached to the network? Includes last
        serving-cell signal (dBm) and neighbour-cell failure count."""
        reach = await check_device_status(ctx.deps.asset_id)
        ctx.deps._reach = reach
        await ctx.deps.tracer.step(
            "Queried CAMARA Device Status.",
            tool="camara.device_status",
            args={"asset_id": ctx.deps.asset_id},
            observation=(
                f"status={reach.status}, signal={reach.signal_strength_dbm} dBm, "
                f"neighbour_failures={reach.neighbor_fail_count}, source={reach.source}"
            ),
        )
        return (
            f"status={reach.status} signal_dbm={reach.signal_strength_dbm} "
            f"neighbour_failures={reach.neighbor_fail_count}"
        )

    @agent.tool
    async def assess_coverage(ctx: RunContext[Deps]) -> str:
        """Interpret the network signals: coverage gap, foreign roaming, or a fault?"""
        if ctx.deps._reach is None:
            return "call check_device_status_tool first"
        v = assess_silence(ctx.deps._reach)
        ctx.deps.verdict = v
        await ctx.deps.tracer.step(f"Interpreting the network signal. {v.explanation}")
        return f"category={v.category} investigate_fault={v.dispatch}: {v.explanation}"

    @agent.tool
    async def resolve_as_roaming(ctx: RunContext[Deps]) -> str:
        """TERMINAL: device is on a foreign network — raise a connectivity ticket, no dispatch."""
        d = ctx.deps
        reach = d._reach
        country = getattr(reach, "country", None) or "a foreign"
        recheck_at = schedule_recheck(d.asset_id, minutes=30)
        await d.tracer.step(
            "Raising a connectivity ticket, not a field job. Nobody is dispatched.",
            tool="ops.notify_operator",
            args={"asset_id": d.asset_id, "queue": "connectivity"},
            observation=f"roaming on {country}; APN unreachable from that network",
        )
        inc = store.incidents[d.incident_id]
        store.set_asset_state(d.asset_id, "blindspot")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="roaming_blocked",
            resolution=(
                f"Device roamed onto a {country} network at the site boundary; its telemetry "
                f"APN no longer reaches us. Machine healthy and attached. Connectivity ticket "
                f"raised, re-check at {recheck_at:%H:%M UTC}. No technician dispatched."
            ),
        )
        _remember(d.asset_id, "roaming_blocked")
        store.publish_kpis()
        d.terminal = "roaming"
        return "resolved as roaming"

    @agent.tool
    async def predict_fault_tool(ctx: RunContext[Deps]) -> str:
        """Run the ML fault classifier on the asset's last telemetry frame."""
        fault = predict_fault(ctx.deps.asset_id, ctx.deps._reach)  # type: ignore[arg-type]
        ctx.deps.last_fault = fault
        await ctx.deps.tracer.step(
            "Ran the ML fault classifier.",
            tool="ml.predict_fault",
            args={"asset_id": ctx.deps.asset_id},
            observation=f"{fault.mode} @ {fault.confidence:.0%}. {fault.rationale}",
        )
        return f"{fault.mode} confidence={fault.confidence:.2f} part={fault.recommended_part}"

    @agent.tool
    async def get_location(ctx: RunContext[Deps]) -> str:
        """CAMARA Location Retrieval: network-verified coordinates for the silent device."""
        loc = await get_device_location(ctx.deps.asset_id)
        ctx.deps.__dict__["_loc"] = loc
        await ctx.deps.tracer.step(
            "Pulled network-verified coordinates.",
            tool="camara.location_retrieval",
            args={"asset_id": ctx.deps.asset_id},
            observation=f"lat={loc.latitude:.5f}, lon={loc.longitude:.5f}, ±{loc.accuracy_m:.0f} m",
        )
        return f"lat={loc.latitude:.5f} lon={loc.longitude:.5f}"

    @agent.tool
    async def resolve_as_blindspot(ctx: RunContext[Deps], reason: str) -> str:
        """TERMINAL: log a cellular blind spot, schedule a re-check, notify the operator, no dispatch."""
        d = ctx.deps
        recheck_at = schedule_recheck(d.asset_id, minutes=15)
        await d.tracer.step(
            "Logged a cellular blind spot. Re-check scheduled, operator notified, no dispatch.",
            tool="ops.schedule_recheck",
            args={"asset_id": d.asset_id, "at": recheck_at.isoformat()},
            observation=reason,
        )
        inc = store.incidents[d.incident_id]
        store.set_asset_state(d.asset_id, "blindspot")
        store.record_blindspot_avoided()
        store.close_incident(
            inc,
            status="network_blindspot",
            resolution=f"Cellular blind spot (agent): {reason} Re-check at {recheck_at:%H:%M UTC}.",
        )
        _remember(d.asset_id, "network_blindspot")
        store.publish_kpis()
        d.terminal = "blindspot"
        return "resolved"

    @agent.tool
    async def dispatch_technician(ctx: RunContext[Deps]) -> str:
        """TERMINAL: create a work order for the predicted fault and route the nearest technician."""
        d = ctx.deps
        fault = d.last_fault or predict_fault(d.asset_id, d._reach)  # type: ignore[arg-type]

        # Guards, not suggestions: terminal tools own these, so no decision the model
        # makes can turn a healthy machine or a roaming one into a field dispatch.
        #
        # These must not depend on the model having called the assessment tool first.
        # It is free to skip straight from device status to dispatch — and when it did,
        # an earlier version of this guard silently did not fire and sent a technician
        # to a machine that had merely crossed a border. Recompute here instead.
        reach = d._reach
        if reach is None:
            reach = await check_device_status(d.asset_id)
            d._reach = reach
        v = d.verdict or assess_silence(reach)  # type: ignore[arg-type]
        if v.category == "roaming_out":
            return await resolve_as_roaming(ctx)

        if getattr(fault, "mode", None) == "NORMAL":
            recheck_at = schedule_recheck(d.asset_id, minutes=15)
            await d.tracer.step(
                "The model finds nothing wrong — this reads as a transient dropout, not a "
                "breakdown. Re-check scheduled instead of a dispatch.",
                tool="ops.schedule_recheck",
                args={"asset_id": d.asset_id, "at": recheck_at.isoformat()},
                observation="no dispatch",
            )
            inc = store.incidents[d.incident_id]
            store.set_asset_state(d.asset_id, "healthy")
            store.record_blindspot_avoided()
            store.close_incident(
                inc,
                status="no_fault",
                resolution=(
                    f"No fault found (agent). Telemetry nominal at {fault.confidence:.0%} "  # type: ignore[union-attr]
                    f"confidence — transient dropout. Re-check at {recheck_at:%H:%M UTC}."
                ),
            )
            _remember(d.asset_id, "no_fault")
            store.publish_kpis()
            d.terminal = "no_fault"
            return "no fault found — dispatch withheld"

        loc = d.__dict__.get("_loc") or await get_device_location(d.asset_id)
        wo = create_work_order(d.incident_id, d.asset_id, fault, loc)  # type: ignore[arg-type]
        await d.tracer.step(
            "Generated work order and assigned the nearest qualified technician.",
            tool="ops.create_work_order",
            args={"incident_id": d.incident_id, "part": wo.part},
            observation=(
                f"{wo.id} -> {wo.technician_name or 'unassigned'} "
                f"({wo.distance_km:.1f} km, ETA {wo.eta_minutes} min)"
            ),
        )
        inc = store.incidents[d.incident_id]
        store.set_asset_state(d.asset_id, "dispatched")
        store.close_incident(
            inc,
            status="hardware_confirmed",
            resolution=(
                f"Hardware fault confirmed (agent): {fault.mode} @ {fault.confidence:.0%}. "  # type: ignore[union-attr]
                f"{wo.id} -> {wo.technician_name} (ETA {wo.eta_minutes} min) with {wo.part}."
            ),
        )
        _remember(d.asset_id, "hardware_confirmed")
        store.publish_kpis()
        d.terminal = "dispatch"
        return f"dispatched {wo.id}"

    return agent


async def run_llm_investigation(incident_id: str) -> None:
    inc = store.incidents[incident_id]
    asset = store.assets[inc.asset_id]
    tracer = Tracer(incident_id)

    inc.status = "investigating"
    store.update_incident(inc)
    await tracer.step(
        f"{asset.label} ({asset.id}) went dark. Investigating autonomously via CAMARA network "
        f"signals before any field action."
    )

    agent = _build_agent()
    deps = Deps(incident_id=incident_id, asset_id=inc.asset_id, tracer=tracer)
    prompt = (
        f"Asset {asset.id} ({asset.label}) at site '{asset.site}' has stopped sending telemetry. "
        f"Investigate and take the correct terminal action."
    )
    result = await agent.run(prompt, deps=deps)

    # Open-weight models intermittently *describe* the final tool call in prose or
    # JSON instead of invoking it — the investigation stalls one step from done,
    # with the diagnosis already made. Rather than throw that work away, ask once
    # more, explicitly. This recovers the run the large majority of the time.
    if deps.terminal is None:
        log.warning(
            "no terminal action for %s (%r) — asking again", incident_id, str(result.output)[:200]
        )
        result = await agent.run(
            "You have not finished. Invoke the terminal tool now as a real tool call: "
            "`resolve_as_blindspot` if this is a coverage gap, otherwise "
            "`dispatch_technician`. Do not reply with text.",
            deps=deps,
            message_history=result.all_messages(),
        )

    if deps.terminal is None:
        # Still nothing — hand off to the deterministic agent.
        log.warning("LLM agent gave up on %s: %r", incident_id, str(result.output)[:200])
        raise RuntimeError("no terminal action")

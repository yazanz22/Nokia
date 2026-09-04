"""Pydantic AI agent (Resource & Tooling Guide §2) driving an open-weights model on
Groq (§3) — see LLM_MODEL. The CAMARA APIs and the ML models are registered as tools
the model chooses to call (§11); this is not a fixed script.

Same actions, same guardrails as ``rule_agent``: the model must finish by calling
exactly one terminal tool (``resolve_as_blindspot`` or ``dispatch_technician``).
If it doesn't, ``run_investigation`` falls back to the rule agent.
"""

from __future__ import annotations

import asyncio
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
1. Then call `check_device_status_tool`. `NOT_CONNECTED` is ambiguous on its own.
2. Use `assess_coverage` to weigh serving-cell signal and neighbour-cell failures:
   - weak signal AND neighbour failures  -> coverage gap.
   - unreachable BUT strong signal, no neighbour failures -> the network is fine; the machine died.
   - reachable BUT roaming on a foreign network -> the machine is fine, its telemetry just
     cannot reach us from that operator. This is a connectivity ticket, never a mechanic.
3. Coverage gap -> call `resolve_as_blindspot`. Do not predict faults, do not dispatch.
4. Foreign roaming -> call `resolve_as_roaming`. Do not predict faults, do not dispatch.
5. Otherwise -> call `predict_fault_tool`, then `get_location`, then `dispatch_technician`.

Tool names are exact. There is no `check_device_status` and no `predict_fault` — the
registered names are `check_device_status_tool` and `predict_fault_tool`. Calling the
wrong name is an error that costs you one of your two retries and tells you nothing.

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


def _already_resolved_reply(d: Deps) -> str:
    """What a terminal tool tells the model when the incident is already closed."""
    return (
        f"ignored: this incident is already resolved as {d.terminal}. An incident closes "
        "once — take no further action."
    )


def _claim_terminal(d: Deps, outcome: str) -> bool:
    """Claim the incident's one terminal outcome. False means another call got there first.

    `Deps.terminal` was written by all four terminal paths and read by none of them, so a
    model that emitted two terminal calls in a single response got both: two resolutions
    over one incident, two work orders, two `record_blindspot_avoided` bumps, and a triage
    sample counted twice. That is not hypothetical — Pydantic AI's default
    `end_strategy='graceful'` runs the function tools of one response *in parallel*, and an
    open-weights model that has just talked itself through the policy will happily call
    `resolve_as_blindspot` and `dispatch_technician` in the same breath.

    Because they run in parallel, checking on entry is not enough: both calls pass an entry
    check long before either reaches its store writes. The test-and-set here is what
    actually decides it — it is synchronous, so the event loop cannot interleave the two
    halves, and exactly one caller can win. Callers claim on the last line before they start
    changing the world; the loser returns having touched nothing. The entry check stays too,
    to spare an obviously-late call a pointless CAMARA round trip first.

    Deliberately *not* claimed before a tool's refusal paths: a blind-spot call the evidence
    rejects has resolved nothing, and must leave the incident open for the model to retry.
    Nor before the internal re-routes (blindspot -> roaming, dispatch -> either), which run
    while the flag is still unset and so pass straight through.
    """
    if d.terminal is not None:
        return False
    d.terminal = outcome
    return True


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
                f"neighbour_failures={reach.neighbor_fail_count}, "
                f"area_congestion={reach.congestion_level or 'n/a'}"
                + (f" @ {reach.congestion_confidence}%"
                   if reach.congestion_confidence is not None else "")
                + f", source={reach.source}"
            ),
        )
        return (
            f"status={reach.status} signal_dbm={reach.signal_strength_dbm} "
            f"neighbour_failures={reach.neighbor_fail_count} "
            f"area_congestion={reach.congestion_level or 'unavailable'} "
            f"congestion_confidence={reach.congestion_confidence}"
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
        if d.terminal is not None:
            return _already_resolved_reply(d)
        reach = d._reach
        if reach is None:
            reach = await check_device_status(d.asset_id)
            d._reach = reach
        # Same rule as the dispatch guard, for the same reason: a terminal tool decides
        # from the network evidence, not from the model's say-so. Closing a genuine
        # breakdown as a roaming ticket strands a broken machine in the desert — the
        # mirror image of a wasted dispatch, and the more expensive mistake.
        if assess_silence(reach).category != "roaming_out":
            return (
                "refused: the device is not attached to a foreign network, so this is not a "
                "roaming event. Reassess with assess_coverage and take the matching action."
            )
        # Claimed here rather than on entry: past the refusal above, which resolves
        # nothing, and before the first line that does. See `_claim_terminal`.
        if not _claim_terminal(d, "roaming"):
            return _already_resolved_reply(d)
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
        return "resolved as roaming"

    @agent.tool
    async def predict_fault_tool(ctx: RunContext[Deps]) -> str:
        """Run the ML fault classifier on the asset's last telemetry frame."""
        # The classifier is only meaningful once we know whether the network can still
        # see the device: `predict_fault` overlays that reality onto the last frame,
        # which the simulator always stamps `reachable=True` because it arrived. Handed
        # `None`, the model is asked about a machine that is both red-hot and answering
        # — a state it never saw in training — and it answers NORMAL, which withholds
        # the dispatch. The model is free to skip the status tool, so fetch it here.
        d = ctx.deps
        if d._reach is None:
            d._reach = await check_device_status(d.asset_id)
        # Off the event loop — scikit-learn inference is CPU-bound, and the first call
        # of the run also parses 33k rows of telemetry history behind it. Inline it
        # stalls the simulator, the detector and every websocket send for ~2s while the
        # dashboard sits frozen mid-investigation.
        fault = await asyncio.to_thread(predict_fault, d.asset_id, d._reach)  # type: ignore[arg-type]
        ctx.deps.last_fault = fault
        await ctx.deps.tracer.step(
            "Ran the ML fault classifier.",
            tool="ml.predict_fault",
            args={"asset_id": ctx.deps.asset_id},
            observation=(f"{fault.mode} @ {fault.confidence:.0%}"
                         + (f", component: {fault.component.replace('_', ' ')}"
                            if fault.component else "")
                         + f". {fault.rationale}"),
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
        if d.terminal is not None:
            return _already_resolved_reply(d)
        reach = d._reach
        if reach is None:
            reach = await check_device_status(d.asset_id)
            d._reach = reach
        # A blind spot is a claim about the network, so the network evidence has to
        # support it. Without this the model can close a real hardware failure as a
        # coverage gap and nobody is ever sent — a silent false negative that looks
        # exactly like the product working.
        v = assess_silence(reach)
        if v.category == "roaming_out":
            return await resolve_as_roaming(ctx)
        if v.category != "coverage_gap":
            return (
                f"refused: the network evidence does not show a coverage gap. {v.explanation} "
                "Run predict_fault_tool and dispatch if the machine is actually broken."
            )
        # Past both refusals and past the roaming re-route — which runs while this flag is
        # still unset, and so is never blocked by its own caller. See `_claim_terminal`.
        if not _claim_terminal(d, "blindspot"):
            return _already_resolved_reply(d)
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
        return "resolved"

    @agent.tool
    async def dispatch_technician(ctx: RunContext[Deps]) -> str:
        """TERMINAL: create a work order for the predicted fault and route the nearest technician."""
        d = ctx.deps
        if d.terminal is not None:
            return _already_resolved_reply(d)

        # Guards, not suggestions: terminal tools own these, so no decision the model
        # makes can turn a healthy machine, a roaming one or a coverage gap into a
        # field dispatch.
        #
        # These must not depend on the model having called the assessment tool first.
        # It is free to skip straight from device status to dispatch — and when it did,
        # an earlier version of this guard silently did not fire and sent a technician
        # to a machine that had merely crossed a border. Recompute here instead.
        #
        # The network reality is also established *before* the classifier runs, not
        # after. `predict_fault` overlays reachability onto the last transmitted frame,
        # and that frame is always stamped reachable — it arrived. Classifying first
        # and backfilling afterwards asks the model about a machine that is both
        # overheating and still answering, and it returns NORMAL: no dispatch, to a
        # machine that is genuinely broken.
        reach = d._reach
        if reach is None:
            reach = await check_device_status(d.asset_id)
            d._reach = reach
        v = d.verdict or assess_silence(reach)  # type: ignore[arg-type]
        if v.category == "roaming_out":
            return await resolve_as_roaming(ctx)
        # A coverage gap is the one outcome this product exists to stop a truck rolling
        # for. The roaming guard was here and this one was not, so a blind-spot frame —
        # the scenario the demo opens with — passed straight through: it is not NORMAL,
        # so the check below let it by, and NETWORK_OUTAGE carries no part, so
        # create_work_order skipped the part filter too. A technician was sent into a
        # dead zone carrying nothing.
        if v.category == "coverage_gap":
            return await resolve_as_blindspot(ctx, v.explanation)

        # Same reason as in `predict_fault_tool`: off the event loop, because a model
        # that dispatches without classifying first pays the full cold cost right here.
        fault = d.last_fault or await asyncio.to_thread(
            predict_fault, d.asset_id, reach  # type: ignore[arg-type]
        )

        # Belt and braces behind the verdict guard: the classifier reads the radio
        # channels itself and can call an outage that the assessment scored as
        # ambiguous (weak signal but no neighbour failures, and no congestion reading
        # to break the tie). There is no part for a coverage gap, so a dispatch here
        # would arrive empty-handed.
        if getattr(fault, "mode", None) == "NETWORK_OUTAGE":
            if not _claim_terminal(d, "blindspot"):
                return _already_resolved_reply(d)
            recheck_at = schedule_recheck(d.asset_id, minutes=15)
            await d.tracer.step(
                "The classifier reads this as the network, not the machine — and there is "
                "no part to carry to a coverage gap. Re-check scheduled, nobody sent.",
                tool="ops.schedule_recheck",
                args={"asset_id": d.asset_id, "at": recheck_at.isoformat()},
                observation="no dispatch",
            )
            inc = store.incidents[d.incident_id]
            store.set_asset_state(d.asset_id, "blindspot")
            store.record_blindspot_avoided()
            store.close_incident(
                inc,
                status="network_blindspot",
                resolution=(
                    f"Cellular blind spot (agent): the fault model attributes the silence to "
                    f"the network at {fault.confidence:.0%} confidence. "  # type: ignore[union-attr]
                    f"Re-check at {recheck_at:%H:%M UTC}. No technician dispatched."
                ),
            )
            _remember(d.asset_id, "network_blindspot")
            store.publish_kpis()
            return "resolved as coverage gap — dispatch withheld"

        if getattr(fault, "mode", None) == "NORMAL":
            if not _claim_terminal(d, "no_fault"):
                return _already_resolved_reply(d)
            recheck_at = schedule_recheck(d.asset_id, minutes=15)
            await d.tracer.step(
                "The model finds nothing wrong — this reads as a transient dropout, not a "
                "breakdown. Re-check scheduled instead of a dispatch.",
                tool="ops.schedule_recheck",
                args={"asset_id": d.asset_id, "at": recheck_at.isoformat()},
                observation="no dispatch",
            )
            inc = store.incidents[d.incident_id]
            # Judged healthy, so the heartbeat has to come back — otherwise the detector
            # re-opens this same incident in thirty seconds and we investigate forever.
            store.resume_telemetry(d.asset_id)
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
            return "no fault found — dispatch withheld"

        # Claimed before the location lookup and the work order, not after: those are the
        # expensive, externally visible half of a dispatch, and a duplicate call that got
        # this far would raise a second work order and mark a second technician busy long
        # before it reached the store writes below.
        if not _claim_terminal(d, "dispatch"):
            return _already_resolved_reply(d)

        # Claiming before the work is done is what stops a duplicate, but it also means a
        # failure below would leave the flag set with nothing created: the model's retry
        # would be told "already resolved", `run_llm_investigation` would see a terminal
        # and not re-ask, and the incident would sit open forever with no work order and
        # no error on screen. So the claim is released if this half raises — the duplicate
        # is still blocked while the work is in flight, which is the window that matters.
        try:
            loc = d.__dict__.get("_loc") or await get_device_location(d.asset_id)
            await d.tracer.step(
                "Locating the available crew — their phones are on the same network as the "
                "machine, so the same call finds whoever is genuinely nearest.",
                tool="camara.location_retrieval",
                args={"subject": "available crew"},
                observation="crew positions refreshed from the network",
            )
            wo = await create_work_order(d.incident_id, d.asset_id, fault, loc)  # type: ignore[arg-type]
            await d.tracer.step(
                "Generated work order and assigned the nearest technician who is actually carrying "
            "the part. Closest is not the same as soonest fixed.",
                tool="ops.create_work_order",
                args={"incident_id": d.incident_id, "part": wo.part},
                observation=(
                    f"{wo.id} -> {wo.technician_name or 'unassigned'} "
                    f"({wo.distance_km:.1f} km, ETA {wo.eta_minutes} min)"
                    + (
                        f". {wo.nearest_skipped_name} is nearer at {wo.nearest_skipped_km:.1f} km but "
                        f"is not carrying a {wo.part}."
                        if wo.nearest_skipped_name
                        else ""
                    )
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
        except Exception:
            d.terminal = None
            raise
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

    # Before any of the recovery below: if the flag and the store disagree, trust the
    # store. A terminal tool that closed the incident and then threw before claiming
    # leaves exactly this state, and every branch under here would then push the model
    # at an incident that is already finished — a second dispatch for a machine someone
    # is already driving to. Same reasoning as `_already_resolved` in `agent/__init__`,
    # applied one level in, where the re-entry is our own re-ask rather than a retry.
    now = store.incidents.get(incident_id)
    if deps.terminal is None and (now is None or now.closed_at is not None):
        log.warning("not re-asking on %s — the incident is no longer open", incident_id)
        return

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

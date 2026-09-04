"""Headless end-to-end check of the closed loop.

Runs the five demo scenarios the way the demo runs them — the real simulator loop
emitting telemetry, the real anomaly detector noticing the silence and opening the
incident, the real agent investigating it — against the mock Network-as-Code layer,
and asserts the terminal state of each:

    blindspot -> incident 'network_blindspot', NO work order, asset 'blindspot'
    roaming   -> incident 'roaming_blocked',   NO work order, asset 'blindspot'
    sensor    -> incident 'sensor_confirmed', 1 work order w/ the cheap kit, asset 'dispatched'
    hardware  -> incident 'hardware_confirmed', 1 work order w/ technician, asset 'dispatched'
    offsite   -> NO incident at all, one geofence alert, asset still 'healthy'

Nothing here opens the incident by hand any more. The detector is part of what can
break — it spent a while dying inside its sweep and swallowing the traceback, which
looked exactly like "no machine ever went silent" — and a pre-demo check that skips
it cannot see that. The cost is wall clock: the script waits for real sweeps and, for
the geofence scenario, for a machine to actually drive the ~30 s out to the perimeter,
so a run takes roughly a minute rather than a few seconds.

AGENT_MODE is deliberately NOT pinned: this script is the only thing that exercises
the LLM agent (the pytest suite pins itself to the rule agent), so it runs whichever
agent the environment is configured for and reports which one resolved each incident.
Run it once as configured for the demo, and once with AGENT_MODE=rule if you want the
deterministic path checked on its own.

Usage:  python scripts/scenario_smoke.py        (exits non-zero on failure)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent import AgentReport, agent_report  # noqa: E402
from app.anomaly import detector  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Incident  # noqa: E402
from app.simulator import simulator  # noqa: E402
from app.store import store  # noqa: E402

# (ok, printable detail, which agent resolved it — None when nothing investigated)
Outcome = tuple[bool, str, AgentReport | None]

# How long to wait for the detector to notice the silence and the agent to finish.
# Generous because AGENT_MODE=llm can sit through two rate-limit back-offs (20 s each)
# before it falls back; the rule agent finishes in a few seconds.
INVESTIGATION_TIMEOUT = 120.0
# The geofence scenario is paced by the machine actually driving: ~5 km per 2 s tick,
# and the fleet is seeded up to 80 km from the site centre.
OFFSITE_TIMEOUT = 120.0
POLL_SECONDS = 0.25


async def _wait_for(predicate, timeout: float) -> bool:
    """Poll until `predicate()` is true. False on timeout — the caller reports it."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(POLL_SECONDS)
    return predicate()


async def _fresh_fleet() -> None:
    """A clean fleet with the simulator and detector both live on it.

    The detector is stopped *before* the store is reset rather than after: an
    investigation still in flight from the previous scenario would otherwise land its
    work order on the fleet we just rebuilt. ``detector.reset()`` then clears the
    in-flight bookkeeping and starts the sweep loop again.
    """
    await detector.stop()
    store.reset()
    simulator.reseed()
    detector.reset()


def _incident_for(asset_id: str) -> Incident | None:
    incidents = [i for i in store.incidents.values() if i.asset_id == asset_id]
    if not incidents:
        return None
    return max(incidents, key=lambda i: i.opened_at)


async def run_one(scenario: str) -> Outcome:
    await _fresh_fleet()
    asset_id = sorted(store.assets)[0]
    label = simulator.inject(asset_id, scenario)

    if scenario == "offsite":
        return await _check_offsite(asset_id, label)
    return await _check_investigation(asset_id, scenario, label)


async def _check_investigation(asset_id: str, scenario: str, label: str) -> Outcome:
    """The four silent-machine scenarios: detector opens it, agent closes it."""
    # `inject` backdates last_seen past the silent threshold, so the very next sweep
    # trips. Waiting for the incident to exist at all is the first thing that can fail
    # and it fails differently from a wrong outcome — say which.
    if not await _wait_for(lambda: _incident_for(asset_id) is not None, INVESTIGATION_TIMEOUT):
        return (
            False,
            f"scenario={scenario} label={label} — the anomaly detector never opened an "
            f"incident for {asset_id} within {INVESTIGATION_TIMEOUT:.0f}s",
            None,
        )

    inc = _incident_for(asset_id)
    assert inc is not None
    # The agent's report is written after the incident is closed, so it is the last
    # thing to appear and the right completion signal to wait on.
    resolved = await _wait_for(
        lambda: inc.closed_at is not None and agent_report(inc.id) is not None,
        INVESTIGATION_TIMEOUT,
    )

    asset = store.assets[asset_id]
    wos = [w for w in store.work_orders.values() if w.incident_id == inc.id]
    report = agent_report(inc.id)

    if not resolved:
        ok = False
    elif scenario == "blindspot":
        ok = (
            inc.status == "network_blindspot"
            and asset.state == "blindspot"
            and len(wos) == 0
            and store.false_dispatches_avoided == 1
        )
    elif scenario == "roaming":
        # Reachable, healthy, and attached — to somebody else's network. Only the
        # roaming half of Device Status reports this, and it is the one dispatch-free
        # outcome that a reachability check on its own would get backwards.
        ok = (
            inc.status == "roaming_blocked"
            and asset.state == "blindspot"
            and len(wos) == 0
            and store.false_dispatches_avoided == 1
        )
    elif scenario == "sensor":
        # The cheap dispatch. It is a *different* outcome from a hardware fault — the
        # machine is fine and only its reporting sensor failed — so the smoke test
        # checks the status and the part, not just that somebody was sent.
        ok = (
            inc.status == "sensor_confirmed"
            and asset.state == "dispatched"
            and len(wos) == 1
            and wos[0].technician_id is not None
            and wos[0].part == "TELEMETRY-SENSOR-KIT"
        )
    else:  # hardware
        ok = (
            inc.status == "hardware_confirmed"
            and asset.state == "dispatched"
            and len(wos) == 1
            and wos[0].technician_id is not None
            and wos[0].part != ""
        )

    agent_name = report.agent if report is not None else "no report"
    detail = (
        f"scenario={scenario} label={label} agent={agent_name} incident={inc.id}/{inc.status} "
        f"asset={asset.state} work_orders={len(wos)}"
        + ("" if resolved else f" (TIMED OUT after {INVESTIGATION_TIMEOUT:.0f}s)")
        + (f" tech={wos[0].technician_name} part={wos[0].part} eta={wos[0].eta_minutes}m" if wos else "")
        + f"\n    resolution: {inc.resolution}"
    )
    return ok, detail, report


async def _check_offsite(asset_id: str, label: str) -> Outcome:
    """The one scenario with no fault in it.

    The machine keeps reporting the whole way out, so nothing goes silent and the
    detector must never see it. The geofence is the only thing that notices, and it
    notices from inside the simulator's tick — which is why this waits for real ticks
    instead of walking the asset west by hand the way the unit tests do.
    """
    found = await _wait_for(
        lambda: any(a.asset_id == asset_id for a in store.geofence_alerts.values()),
        OFFSITE_TIMEOUT,
    )
    asset = store.assets[asset_id]
    alerts = [a for a in store.geofence_alerts.values() if a.asset_id == asset_id]
    ok = (
        found
        and len(alerts) == 1
        and asset.offsite is True
        and asset.state == "healthy"
        # A crossing that opened an incident or sent anyone has become a slower,
        # worse version of the roaming outcome.
        and _incident_for(asset_id) is None
        and len(store.work_orders) == 0
        and store.incidents_prevented == 1
    )
    detail = (
        f"scenario=offsite label={label} asset={asset.state} offsite={asset.offsite} "
        f"alerts={len(alerts)} incidents={len(store.incidents)} "
        f"work_orders={len(store.work_orders)}"
        + ("" if found else f" (TIMED OUT after {OFFSITE_TIMEOUT:.0f}s)")
        + (f"\n    alert: {alerts[0].id} {alerts[0].distance_km} km past the perimeter"
           f" (source={alerts[0].source})" if alerts else "")
    )
    # No incident, so no investigation, so no agent report — and deliberately not the
    # module-level summary, which would still be carrying the previous scenario's label.
    return ok, detail, None


async def main() -> int:
    settings = get_settings()
    print(f"AGENT_MODE={settings.agent_mode}  NAC_MODE={settings.nac_mode}")
    if settings.agent_mode == "llm":
        print(f"LLM_MODEL={settings.llm_model}")

    rc = 0
    fallbacks: list[str] = []
    try:
        for scenario in ("blindspot", "roaming", "sensor", "hardware", "offsite"):
            ok, detail, report = await run_one(scenario)
            print(("PASS " if ok else "FAIL ") + detail)
            if not ok:
                rc = 1
            # Each scenario's own report, not the module-level ``last_agent_used``
            # summary. That summary is scoped to the current fleet epoch and every
            # scenario resets the fleet, so by the end of the loop it can only describe
            # the last scenario — and the geofence scenario runs no investigation at
            # all, which would leave it reporting a stale label from the run before.
            # Checking every scenario also means a fallback in the first one is not
            # hidden by four later successes.
            if report is not None and "fallback" in report.agent:
                fallbacks.append(f"{scenario}: {report.error}")
    finally:
        await detector.stop()
        await simulator.stop()

    # A silent fallback to the rule agent still produces correct outcomes, so it
    # would otherwise read as a clean pass — while the model you intended to demo
    # is not running at all. Fail loudly instead.
    if settings.agent_mode == "llm" and fallbacks:
        print("\nFAIL  AGENT_MODE=llm but the model never ran:")
        for line in fallbacks:
            print(f"      {line}")
        rc = 1

    print("\nsmoke:", "OK" if rc == 0 else "FAILURES")
    return rc


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

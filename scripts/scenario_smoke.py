"""Headless end-to-end check of the closed loop.

Runs both demo scenarios through the real anomaly detector + agent (rule mode,
mock Network-as-Code) and asserts the terminal state:

    blindspot -> incident 'network_blindspot', NO work order, asset 'blindspot'
    hardware  -> incident 'hardware_confirmed', 1 work order w/ technician, asset 'dispatched'

Usage:  python scripts/scenario_smoke.py        (exits non-zero on failure)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent import run_investigation  # noqa: E402
from app.simulator import simulator  # noqa: E402
from app.store import store  # noqa: E402


async def run_one(scenario: str) -> tuple[bool, str]:
    store.reset()
    simulator.reseed()
    asset_id = sorted(store.assets)[0]

    label = simulator.inject(asset_id, scenario)
    # The detector normally opens the incident; do it directly here so the test
    # doesn't depend on loop timing.
    inc = store.open_incident(asset_id, summary=f"[smoke] {asset_id} silent")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)

    inc = store.incidents[inc.id]
    asset = store.assets[asset_id]
    wos = [w for w in store.work_orders.values() if w.incident_id == inc.id]

    if scenario == "blindspot":
        ok = (
            inc.status == "network_blindspot"
            and asset.state == "blindspot"
            and len(wos) == 0
            and store.false_dispatches_avoided == 1
        )
    else:  # hardware
        ok = (
            inc.status == "hardware_confirmed"
            and asset.state == "dispatched"
            and len(wos) == 1
            and wos[0].technician_id is not None
            and wos[0].part != ""
        )
    detail = (
        f"scenario={scenario} label={label} incident={inc.status} asset={asset.state} "
        f"work_orders={len(wos)}"
        + (f" tech={wos[0].technician_name} part={wos[0].part} eta={wos[0].eta_minutes}m" if wos else "")
        + f"\n    resolution: {inc.resolution}"
    )
    return ok, detail


async def main() -> int:
    rc = 0
    for scenario in ("blindspot", "hardware"):
        ok, detail = await run_one(scenario)
        print(("PASS " if ok else "FAIL ") + detail)
        if not ok:
            rc = 1
    print("\nsmoke:", "OK" if rc == 0 else "FAILURES")
    return rc


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

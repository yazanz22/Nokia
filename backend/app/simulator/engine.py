"""Telemetry simulator.

Every tick it emits a fresh :class:`TelemetrySample` for each demo asset, drawn
from that asset's real dataset readings. When a scenario is injected the asset
"goes silent" (stops emitting) and its ``pending_label`` is exposed so the
dataset-backed Network-as-Code mock and the ML client know what situation the
asset is really in — the agent, of course, does not.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from datetime import timedelta

from ..config import get_settings
from ..models import TelemetrySample, utcnow
from ..store import store
from .profiles import build_profiles

# Scenario name -> dataset label
SCENARIOS = {
    "blindspot": "NETWORK_OUTAGE",
    "hardware": "DEVICE_FAILURE",
    "sensor": "SENSOR_FAILURE",
    # Not a dataset label: the machine crossed onto a foreign operator near the site
    # boundary, so it is healthy and attached but its telemetry no longer reaches us.
    # Synthesised by the NaC mock — see nac/mock.py.
    "roaming": "ROAMING_OUT",
}


class SimulatorEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._profiles = {}
        self._rng = random.Random(2026)
        # asset_id -> dataset label the asset is currently really experiencing
        self._pending: dict[str, str] = {}
        # assets that have stopped emitting telemetry (heartbeat lost)
        self._silent: set[str] = set()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self) -> None:
        self._profiles = build_profiles(list(store.assets.keys()))
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="simulator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def reseed(self) -> None:
        """After store.reset() — rebuild profiles and clear scenario state."""
        self._profiles = build_profiles(list(store.assets.keys()))
        self._pending.clear()
        self._silent.clear()

    # ── scenario control (called by the /scenarios route) ────────────────
    def inject(self, asset_id: str, scenario: str) -> str:
        if asset_id not in store.assets:
            raise KeyError(asset_id)
        if scenario not in SCENARIOS:
            raise ValueError(scenario)
        label = SCENARIOS[scenario]
        self._pending[asset_id] = label
        prof = self._profiles.get(asset_id)

        # Emit one final "distress" reading (the last CAN-bus frame before the
        # uplink dropped) so the dashboard shows the anomaly and the ML model has
        # a real fault reading to classify. Then the asset goes silent.
        if prof is not None:
            row = prof.next_row(label) or prof.next_normal()
            if row is not None:
                store.record_telemetry(
                    TelemetrySample(
                        asset_id=asset_id,
                        ts=utcnow(),
                        reachable=True,
                        telemetry_age_sec=5.0,
                        signal_strength_dbm=row["signal_strength_dbm"],
                        neighbor_fail_count=row["neighbor_fail_count"],
                        engine_temp_c=row["engine_temp_c"],
                        ground_truth=label,
                    )
                )
        store.set_asset_state(asset_id, "anomaly")

        self._silent.add(asset_id)
        # Freeze last_seen in the past so the anomaly detector trips promptly.
        asset = store.assets[asset_id]
        asset.last_seen = utcnow() - timedelta(seconds=get_settings().silent_threshold_seconds + 5)
        return label

    def clear(self, asset_id: str) -> None:
        self._pending.pop(asset_id, None)
        self._silent.discard(asset_id)

    def pending_label(self, asset_id: str) -> str | None:
        """What the asset is really experiencing (dataset label), or None."""
        return self._pending.get(asset_id)

    def is_silent(self, asset_id: str) -> bool:
        return asset_id in self._silent

    # ── main loop ────────────────────────────────────────────────────────
    async def _run(self) -> None:
        settings = get_settings()
        while True:
            now = utcnow()
            for asset_id, asset in list(store.assets.items()):
                if asset_id in self._silent:
                    continue  # heartbeat lost — emit nothing
                prof = self._profiles.get(asset_id)
                if prof is None:
                    continue
                row = prof.next_normal()
                if row is None:
                    continue
                # Gentle positional drift so the map feels alive.
                asset.latitude += self._rng.uniform(-0.0008, 0.0008)
                asset.longitude += self._rng.uniform(-0.0008, 0.0008)
                sample = TelemetrySample(
                    asset_id=asset_id,
                    ts=now,
                    reachable=True,
                    telemetry_age_sec=max(0.0, row["telemetry_age_sec"]),
                    signal_strength_dbm=row["signal_strength_dbm"],
                    neighbor_fail_count=row["neighbor_fail_count"],
                    engine_temp_c=row["engine_temp_c"],
                    ground_truth="NORMAL",
                )
                store.record_telemetry(sample)
            # Crews drive between jobs. A stationary technician would make locating
            # them pointless — you ask precisely because they have moved.
            for tech in store.technicians.values():
                if tech.available:
                    tech.latitude += self._rng.uniform(-0.0015, 0.0015)
                    tech.longitude += self._rng.uniform(-0.0015, 0.0015)
            store.advance_work_orders()
            store.publish_kpis()
            await asyncio.sleep(settings.sim_tick_seconds)


simulator = SimulatorEngine()

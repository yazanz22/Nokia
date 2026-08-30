"""Dataset-backed Network-as-Code mock.

Deterministic and realistic: it replays real ``dataset1.csv`` rows for the asset.
If the simulator has a scenario pending for the asset, it serves a row of that
label (NETWORK_OUTAGE / DEVICE_FAILURE / SENSOR_FAILURE); otherwise a NORMAL row.
A small artificial latency keeps the agent trace legible on screen.
"""

from __future__ import annotations

import asyncio
import random

from ..seed import asset_pool
from .base import DeviceLocation, Reachability, _now


class MockNaCClient:
    source = "mock"

    def __init__(self, latency_seconds: float = 0.6) -> None:
        self._latency = latency_seconds
        self._rng = random.Random(99)

    def _row_for(self, asset_id: str) -> dict:
        from ..simulator.engine import simulator  # local import avoids a cycle

        pool = asset_pool().get(asset_id, {})
        label = simulator.pending_label(asset_id) or "NORMAL"
        rows = pool.get(label) or pool.get("NORMAL") or []
        if not rows:
            # Asset not in dataset — synthesise a benign reading.
            return {
                "reachable": True,
                "signal_strength_dbm": -60.0,
                "neighbor_fail_count": 0,
                "latitude": 27.6,
                "longitude": 35.0,
            }
        return self._rng.choice(rows)

    async def get_reachability(self, asset_id: str) -> Reachability:
        await asyncio.sleep(self._latency)
        row = self._row_for(asset_id)
        status = "CONNECTED_DATA" if row["reachable"] else "NOT_CONNECTED"
        return Reachability(
            asset_id=asset_id,
            status=status,
            signal_strength_dbm=row["signal_strength_dbm"],
            neighbor_fail_count=row["neighbor_fail_count"],
            as_of=_now(),
            source="mock",
        )

    async def get_location(self, asset_id: str) -> DeviceLocation:
        await asyncio.sleep(self._latency)
        row = self._row_for(asset_id)
        return DeviceLocation(
            asset_id=asset_id,
            latitude=row["latitude"],
            longitude=row["longitude"],
            accuracy_m=self._rng.uniform(15.0, 60.0),
            as_of=_now(),
            source="mock",
        )

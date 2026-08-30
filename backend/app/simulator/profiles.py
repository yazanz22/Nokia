"""Per-asset samplers over the real dataset rows.

Each asset gets a shuffled, repeating cycle of its own readings for every label.
The simulator pulls NORMAL readings during steady state and a specific label's
readings when a scenario is injected.
"""

from __future__ import annotations

import random
from typing import Any

from ..seed import asset_pool


class AssetProfile:
    def __init__(self, asset_id: str, seed: int) -> None:
        self.asset_id = asset_id
        self._rng = random.Random(seed)
        self._cycles: dict[str, list[dict[str, Any]]] = {}
        self._idx: dict[str, int] = {}
        pool = asset_pool().get(asset_id, {})
        for label, rows in pool.items():
            shuffled = list(rows)
            self._rng.shuffle(shuffled)
            self._cycles[label] = shuffled
            self._idx[label] = 0

    def has(self, label: str) -> bool:
        return bool(self._cycles.get(label))

    def next_row(self, label: str) -> dict[str, Any] | None:
        rows = self._cycles.get(label)
        if not rows:
            return None
        i = self._idx[label] % len(rows)
        self._idx[label] = i + 1
        return rows[i]

    def next_normal(self) -> dict[str, Any] | None:
        row = self.next_row("NORMAL")
        if row is None:
            return None
        # Small perturbation so consecutive ticks aren't identical.
        jitter = self._rng.uniform(-1.5, 1.5)
        return {
            **row,
            "engine_temp_c": max(60.0, row["engine_temp_c"] + jitter),
            "signal_strength_dbm": row["signal_strength_dbm"] + self._rng.uniform(-2, 2),
            "telemetry_age_sec": max(0.0, row["telemetry_age_sec"] + self._rng.uniform(-3, 3)),
        }


def build_profiles(asset_ids: list[str]) -> dict[str, AssetProfile]:
    return {aid: AssetProfile(aid, seed=hash(aid) & 0xFFFF) for aid in asset_ids}

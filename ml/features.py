"""Feature builders shared by training (``ml/train.py``) and inference
(``backend/app/ml/``). Keep the two in lockstep — the column order here *is* the
model's input contract.

Two separate feature sets, because there are two separate questions:

* :func:`diagnostic_features` — one network+telemetry reading in, "what broke?" out.
* :func:`prognostic_features` — a *window* of readings in, "is this heading for
  failure?" out. Trends live here; a single reading cannot express one.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# ── Diagnosis (dataset1.csv) ────────────────────────────────────────────────

DIAGNOSTIC_FEATURES = [
    "telemetry_age_sec",
    "signal_strength_dbm",
    "neighbor_fail_count",
    "engine_temp_c",
    "reachable",
]

DIAGNOSTIC_CLASSES = ["NORMAL", "NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE"]


def diagnostic_features(reading: dict) -> list[float]:
    return [
        float(reading["telemetry_age_sec"]),
        float(reading["signal_strength_dbm"]),
        float(reading["neighbor_fail_count"]),
        float(reading["engine_temp_c"]),
        1.0 if reading["reachable"] in (True, "True", "true", 1, "1") else 0.0,
    ]


# ── Prognosis (telemetry_history.csv) ───────────────────────────────────────

# Channels ordered by how early they move for a hydraulic pump: vibration and oil
# particles give days of warning, pressure hours, temperature minutes. Other
# components move them in a different order, which is what makes them separable.
CHANNELS = [
    "vibration_mm_s",
    "oil_particle_count",
    "hydraulic_pressure_bar",
    "engine_temp_c",
    # Purely electrical faults move nothing mechanical, so without this channel an
    # alternator failure is invisible and gets mistaken for whatever else is drifting.
    "battery_voltage_v",
]

# Readings per window. At 6-hourly sampling, 8 readings = the trailing 2 days.
WINDOW = 8

PROGNOSTIC_FEATURES = [
    f"{ch}_{stat}" for ch in CHANNELS for stat in ("last", "mean", "std", "slope", "delta")
] + ["engine_hours"]


def _slope(values: Sequence[float]) -> float:
    """Least-squares gradient per reading. The single most useful signal here —
    it is what separates 'runs hot' from 'getting hotter'."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)
    x_mean, y_mean = x.mean(), y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((x - x_mean) * (y - y_mean)).sum() / denom)


def prognostic_features(window: Sequence[dict]) -> list[float]:
    """Build one feature row from a trailing window of readings (oldest first).

    Shorter windows are accepted so an asset can be scored before it has a full
    two days of history — the stats simply get noisier.
    """
    if not window:
        raise ValueError("empty window")
    feats: list[float] = []
    for ch in CHANNELS:
        series = [float(r[ch]) for r in window]
        arr = np.asarray(series, dtype=float)
        feats.extend(
            [
                float(arr[-1]),
                float(arr.mean()),
                float(arr.std()),
                _slope(series),
                float(arr[-1] - arr[0]),
            ]
        )
    feats.append(float(window[-1].get("engine_hours", 0.0)))
    return feats


# What each component failure needs on the truck. Naming the part is the difference
# between "something is wrong" and a first-time fix.
COMPONENT_PARTS: dict[str, tuple[str, int]] = {
    "hydraulic_pump": ("HYD-PUMP-40L", 3),
    "cooling_system": ("RADIATOR-CORE-XL", 2),
    "main_bearing": ("BEARING-SET-90", 4),
    "alternator": ("ALTERNATOR-24V", 1),
}
COMPONENT_CLASSES = list(COMPONENT_PARTS)

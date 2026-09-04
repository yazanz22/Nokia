"""Feature builders shared by training (``ml/train.py``) and inference
(``backend/app/ml/``). Keep the two in lockstep — the column order here *is* the
model's input contract.

Two separate feature sets, because there are two separate questions:

* :func:`diagnostic_features` — one network+telemetry reading in, "what broke?" out.
* :func:`prognostic_features` — a *window* of readings in, "is this heading for
  failure?" out. Trends live here; a single reading cannot express one.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

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


# ── Repair gaps ─────────────────────────────────────────────────────────────
#
# A window is only a trend if the readings in it come from the same continuous run
# of the same machine. They do not always. ``data/history_builder.py`` sends a
# machine to the workshop for ~2 days after each failure and emits nothing while it
# is there — it simply skips those steps, so nothing in the CSV marks them. The
# repair leaves a hole in the series, and a window that straddles one has its
# slope/std/delta computed *across* a repair. The machine before the hole and the
# machine after it are physically different states: a worn-out pump on one side, a
# rebuilt one on the other. That is not a trend, it is an artefact.
#
# Detection is by timestamp delta, because there is no column to read. The history
# is sampled every 6 hours, and the observed deltas are cleanly bimodal — 6h between
# consecutive readings, 54h across a repair (9 steps: the 8 missing ones plus the
# step itself) — so a threshold at 1.5x the nominal stride has a wide margin on
# both sides and is not tuned to the generator's exact repair length.
#
# This lives here, once, because training (``ml/train.py``) and inference
# (``backend/app/ml/forecast.py``) MUST agree. A model trained only on gap-free
# windows and served windows that span gaps is train/serve skew — a worse bug than
# the one this fixes, and a silent one.

NOMINAL_STEP_HOURS = 6.0
MAX_GAP_HOURS = NOMINAL_STEP_HOURS * 1.5


def _as_datetime(value: Any) -> datetime | None:
    """Timestamps reach us as ``datetime`` from the API layer and as strings from
    ``pandas.read_csv``. Normalise both; return None for anything unreadable."""
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "nat", "none"):
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def window_is_contiguous(
    window: Sequence[dict], max_gap_hours: float = MAX_GAP_HOURS
) -> bool:
    """True if no two consecutive readings in ``window`` straddle a repair gap.

    A window whose timestamps cannot be read is reported as *not* contiguous. We
    cannot prove such a window is gap-free, and quietly treating it as one is how
    the original bug got in — the loud failure (the asset goes unscored) is the
    safer of the two.
    """
    if len(window) < 2:
        return True
    stamps = [_as_datetime(r.get("timestamp")) for r in window]
    if any(s is None for s in stamps):
        return False
    for prev, cur in zip(stamps, stamps[1:]):
        if (cur - prev).total_seconds() / 3600.0 > max_gap_hours:
            return False
    return True


def contiguous_windows(
    records: Sequence[dict], size: int = WINDOW
) -> Iterator[tuple[int, Sequence[dict]]]:
    """Every gap-free window of ``size`` readings, as ``(end_index, window)``.

    ``records`` must be one asset's readings, oldest first. Used by training; the
    serving side takes the single trailing window via :func:`trailing_window`, and
    both go through :func:`window_is_contiguous` so the rule cannot drift apart.
    """
    for i in range(size - 1, len(records)):
        window = records[i - size + 1 : i + 1]
        if window_is_contiguous(window):
            yield i, window


def trailing_window(records: Sequence[dict], size: int = WINDOW) -> Sequence[dict] | None:
    """The most recent ``size`` readings, or None if they do not form a gap-free
    window — which is exactly the set of windows training was allowed to see.

    Returning None means "no opinion" rather than a guess. An asset just out of the
    workshop is unscoreable until it has ``size`` readings of its new life, which is
    the honest answer: the model has nothing to extrapolate from yet.
    """
    if len(records) < size:
        return None
    window = records[-size:]
    return window if window_is_contiguous(window) else None


# What each component failure needs on the truck. Naming the part is the difference
# between "something is wrong" and a first-time fix.
COMPONENT_PARTS: dict[str, tuple[str, int]] = {
    "hydraulic_pump": ("HYD-PUMP-40L", 3),
    "cooling_system": ("RADIATOR-CORE-XL", 2),
    "main_bearing": ("BEARING-SET-90", 4),
    "alternator": ("ALTERNATOR-24V", 1),
}
COMPONENT_CLASSES = list(COMPONENT_PARTS)

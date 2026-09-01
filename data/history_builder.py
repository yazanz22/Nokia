"""Generator for ``telemetry_history.csv`` — continuous per-asset telemetry used to
train the **prognostic** (failure-forecasting) model.

This is a different thing from ``dataset1.csv``, and both are needed:

* ``dataset1.csv``        — point-in-time network + telemetry snapshots. Answers
                            *"this machine just went silent — what broke?"* (diagnosis)
* ``telemetry_history.csv`` — a continuous 6-hourly reading per asset over 30 days.
                            Answers *"which machines are going to break?"* (prognosis)

## The degradation model

A hydraulic pump doesn't fail instantly, and the signals do not all arrive at once.
That ordering is the whole reason this needs a model rather than a threshold:

    t-5d ──▶ bearing wear starts
             · vibration_mm_s creeps up          ◀── EARLY, days of warning
             · oil_particle_count rises          ◀── EARLY
    t-2d ──▶ seals begin passing
             · hydraulic_pressure_bar sags       ◀── MID
    t-8h ──▶ pump working against itself
             · engine_temp_c climbs              ◀── LATE, hours of warning
    t-0  ──▶ failure. Machine stops. Telemetry goes dark.

Engine temperature — the only signal ``dataset1.csv`` carries — is the *last* one to
move. A temperature threshold catches the failure with hours to spare. Vibration and
oil-particle *trends* catch it with days to spare. That gap is the product.

Healthy assets get the same channels with normal wear and seasonal drift, so the model
has to learn the trend shape rather than a level.

    python data/history_builder.py --out data/telemetry_history.csv --seed 7
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Baselines for a healthy machine under load.
BASE_VIBRATION = 2.4      # mm/s RMS
BASE_PARTICLES = 120.0    # ISO particle count per ml
BASE_PRESSURE = 210.0     # bar
BASE_TEMP = 82.0          # deg C

READINGS_PER_DAY = 4      # 6-hourly
DEGRADE_DAYS = 5.0        # how long the run-to-failure ramp lasts


def _degradation(progress: float) -> tuple[float, float, float, float]:
    """Signal multipliers/offsets at ``progress`` through the failure ramp (0..1).

    Each channel has its own onset, so the signals arrive in physical order.
    """
    # Vibration: starts immediately, roughly linear then accelerating.
    vib = 3.9 * (progress ** 1.5)
    # Oil particles: starts immediately, accelerating harder (metal shedding).
    part = 640.0 * (progress ** 2.0)
    # Pressure: nothing until ~60% through, then falls away.
    p = max(0.0, (progress - 0.60) / 0.40)
    press = -46.0 * (p ** 1.4)
    # Temperature: nothing until ~93% through (the last ~8 hours), then spikes.
    t = max(0.0, (progress - 0.93) / 0.07)
    temp = 44.0 * (t ** 1.2)
    return vib, part, press, temp


def generate(
    n_assets: int = 500,
    days: int = 30,
    failure_rate: float = 0.18,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)

    end = datetime(2026, 8, 31, 0, 0, 0)
    step = timedelta(hours=24 // READINGS_PER_DAY)
    n_steps = days * READINGS_PER_DAY
    stamps = [end - step * (n_steps - i) for i in range(n_steps)]

    asset_ids = [f"EQ-{i:04d}" for i in range(1, n_assets + 1)]
    rows: list[dict] = []

    for asset_id in asset_ids:
        # Per-machine character: an old loader runs hotter and shakier than a new one.
        vib_bias = float(rng.normal(0, 0.35))
        part_bias = float(rng.normal(0, 18.0))
        press_bias = float(rng.normal(0, 7.0))
        temp_bias = float(rng.normal(0, 3.0))
        engine_hours = float(rng.uniform(400, 14_000))

        # Does this machine fail inside the window, and when?
        fails = py_rng.random() < failure_rate
        # Place the failure so the full ramp is visible in-window.
        fail_idx = (
            py_rng.randint(int(DEGRADE_DAYS * READINGS_PER_DAY) + 2, n_steps - 1)
            if fails
            else None
        )

        for i, ts in enumerate(stamps):
            # Duty cycle — machines work days, idle nights.
            hour = ts.hour
            duty = 1.0 if 6 <= hour < 18 else 0.55
            # Slow seasonal/ambient drift so levels alone aren't diagnostic.
            drift = math.sin(i / n_steps * math.pi * 2) * 1.5

            vib = BASE_VIBRATION + vib_bias + duty * 0.4 + float(rng.normal(0, 0.22))
            part = BASE_PARTICLES + part_bias + engine_hours * 0.004 + float(rng.normal(0, 11.0))
            press = BASE_PRESSURE + press_bias - duty * 3.0 + float(rng.normal(0, 3.4))
            temp = BASE_TEMP + temp_bias + duty * 6.0 + drift + float(rng.normal(0, 2.1))

            hours_to_failure = None
            if fail_idx is not None and i <= fail_idx:
                hours_left = (fail_idx - i) * (24 / READINGS_PER_DAY)
                hours_to_failure = hours_left
                ramp_hours = DEGRADE_DAYS * 24
                if hours_left <= ramp_hours:
                    progress = 1.0 - (hours_left / ramp_hours)
                    d_vib, d_part, d_press, d_temp = _degradation(progress)
                    vib += d_vib
                    part += d_part
                    press += d_press
                    temp += d_temp

            # After it fails the machine is dark — emit nothing.
            if fail_idx is not None and i > fail_idx:
                break

            rows.append(
                {
                    "timestamp": ts,
                    "device_id": asset_id,
                    "engine_hours": round(engine_hours + i * 1.4 * duty, 1),
                    "vibration_mm_s": round(max(0.2, vib), 3),
                    "oil_particle_count": round(max(10.0, part), 1),
                    "hydraulic_pressure_bar": round(press, 2),
                    "engine_temp_c": round(temp, 2),
                    "hours_to_failure": (
                        round(hours_to_failure, 1) if hours_to_failure is not None else ""
                    ),
                    "will_fail_72h": int(
                        hours_to_failure is not None and hours_to_failure <= 72
                    ),
                }
            )

    df = pd.DataFrame(rows)
    n_fail_assets = df[df["will_fail_72h"] == 1]["device_id"].nunique()
    print(f"Generated {len(df):,} readings across {df['device_id'].nunique()} assets.")
    print(f"  assets entering failure within the window : {n_fail_assets}")
    print(f"  readings labelled will_fail_72h=1         : {int(df['will_fail_72h'].sum()):,}")
    return df


def main() -> None:
    default_out = Path(__file__).resolve().parent / "telemetry_history.csv"
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--assets", type=int, default=500)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.out == default_out and args.out.exists():
        raise SystemExit(
            f"refusing to overwrite the canonical {args.out.name}; "
            "pass --out <path> or delete it first"
        )

    df = generate(args.assets, args.days, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    size_mb = args.out.stat().st_size / 1e6
    print(f"wrote {args.out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

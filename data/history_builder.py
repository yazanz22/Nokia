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
BASE_VOLTAGE = 27.8       # V, 24V system under charge

READINGS_PER_DAY = 4      # 6-hourly
DEGRADE_DAYS = 5.0        # how long the run-to-failure ramp lasts


# ── What actually breaks, and how each one announces itself ──────────────────
#
# A dispatch is only as good as the part on the truck, so the model has to name the
# component rather than just say "hardware". Each of these fails with a different
# signature across the same five channels, which is what makes them separable:
#
#   hydraulic_pump   bearing wear -> vibration and metal in the oil, then pressure
#                    sags as seals pass, then temperature spikes at the very end
#   cooling_system   temperature climbs early and stays climbing; nothing else moves
#   main_bearing     vibration dominates from the start, some metal, little else
#   alternator       purely electrical: charge voltage decays, mechanics stay normal
#
# The point is that temperature — the channel a threshold alarm watches — is the
# last to move for the pump, never moves for the alternator, and is the *only*
# signal for cooling. One threshold cannot tell these apart.
COMPONENTS = ("hydraulic_pump", "cooling_system", "main_bearing", "alternator")
COMPONENT_WEIGHTS = (0.45, 0.22, 0.21, 0.12)


def _degradation(component: str, progress: float) -> tuple[float, float, float, float, float]:
    """Channel offsets at ``progress`` (0..1) through this component's failure ramp.

    Returns (vibration, oil particles, hydraulic pressure, engine temp, voltage).
    """
    vib = part = press = temp = volt = 0.0

    if component == "hydraulic_pump":
        vib = 3.9 * (progress ** 1.5)
        part = 640.0 * (progress ** 2.0)
        p = max(0.0, (progress - 0.60) / 0.40)      # seals start passing at ~60%
        press = -46.0 * (p ** 1.4)
        t = max(0.0, (progress - 0.93) / 0.07)      # heat only in the last ~8 hours
        temp = 44.0 * (t ** 1.2)

    elif component == "cooling_system":
        # Heat is the whole story, and it starts early — the opposite of the pump.
        temp = 40.0 * (progress ** 1.15)
        vib = 0.35 * progress                        # negligible
        press = -4.0 * progress

    elif component == "main_bearing":
        # Violent mechanically, quiet everywhere else until the very end.
        vib = 7.8 * (progress ** 1.3)
        part = 300.0 * (progress ** 2.2)
        t = max(0.0, (progress - 0.85) / 0.15)
        temp = 14.0 * t

    elif component == "alternator":
        # Nothing mechanical at all: the charge system simply decays.
        volt = -4.6 * (progress ** 1.6)
        temp = 3.0 * progress

    return vib, part, press, temp, volt


def generate(
    n_assets: int = 500,
    days: int = 30,
    failure_rate: float = 0.16,
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

        # Failure cycles. A machine that fails gets repaired and goes back to work,
        # so one asset can run through several degrade -> fail -> repair cycles in a
        # 30-day window. Modelling that matters: with a single terminal failure per
        # asset, almost nothing is ever caught mid-ramp, which is exactly the state
        # the forecasting model exists to detect.
        ramp_steps = int(DEGRADE_DAYS * READINGS_PER_DAY)
        repair_steps = READINGS_PER_DAY * 2  # ~2 days out of service
        fail_points: list[int] = []
        fail_components: dict[int, str] = {}
        # Start each machine at its own random offset and advance by a jittered
        # stride, otherwise every asset fails on the same grid of indices and the
        # fleet's time-to-failure values come out suspiciously identical.
        cursor = ramp_steps + 2 + py_rng.randint(0, ramp_steps)
        while cursor < n_steps:
            if py_rng.random() < failure_rate:
                fail_points.append(cursor)
                fail_components[cursor] = py_rng.choices(COMPONENTS, COMPONENT_WEIGHTS)[0]
                cursor += repair_steps + ramp_steps + py_rng.randint(0, ramp_steps)
            else:
                cursor += py_rng.randint(2, max(3, ramp_steps))
        # Steps during which the machine is in the workshop, emitting nothing.
        down = {i for f in fail_points for i in range(f + 1, f + 1 + repair_steps)}

        def _next_failure(i: int) -> int | None:
            for f in fail_points:
                if f >= i:
                    return f
            return None

        for i, ts in enumerate(stamps):
            if i in down:
                continue
            # Duty cycle — machines work days, idle nights.
            hour = ts.hour
            duty = 1.0 if 6 <= hour < 18 else 0.55
            # Slow seasonal/ambient drift so levels alone aren't diagnostic.
            drift = math.sin(i / n_steps * math.pi * 2) * 1.5

            vib = BASE_VIBRATION + vib_bias + duty * 0.4 + float(rng.normal(0, 0.22))
            part = BASE_PARTICLES + part_bias + engine_hours * 0.004 + float(rng.normal(0, 11.0))
            press = BASE_PRESSURE + press_bias - duty * 3.0 + float(rng.normal(0, 3.4))
            temp = BASE_TEMP + temp_bias + duty * 6.0 + drift + float(rng.normal(0, 2.1))
            volt = BASE_VOLTAGE + float(rng.normal(0, 0.18))

            hours_to_failure = None
            failing_component = ""
            nxt = _next_failure(i)
            if nxt is not None:
                hours_left = (nxt - i) * (24 / READINGS_PER_DAY)
                hours_to_failure = hours_left
                ramp_hours = DEGRADE_DAYS * 24
                component = fail_components.get(nxt, COMPONENTS[0])
                if hours_left <= ramp_hours:
                    progress = 1.0 - (hours_left / ramp_hours)
                    d_vib, d_part, d_press, d_temp, d_volt = _degradation(component, progress)
                    vib += d_vib
                    part += d_part
                    press += d_press
                    temp += d_temp
                    volt += d_volt
                    failing_component = component

            rows.append(
                {
                    "timestamp": ts,
                    "device_id": asset_id,
                    "engine_hours": round(engine_hours + i * 1.4 * duty, 1),
                    "vibration_mm_s": round(max(0.2, vib), 3),
                    "oil_particle_count": round(max(10.0, part), 1),
                    "hydraulic_pressure_bar": round(press, 2),
                    "engine_temp_c": round(temp, 2),
                    "battery_voltage_v": round(volt, 3),
                    "hours_to_failure": (
                        round(hours_to_failure, 1) if hours_to_failure is not None else ""
                    ),
                    "will_fail_72h": int(
                        hours_to_failure is not None and hours_to_failure <= 72
                    ),
                    # Which component is on its way out, once the ramp has begun.
                    "failing_component": failing_component,
                }
            )

    df = pd.DataFrame(rows)
    n_fail_assets = df[df["will_fail_72h"] == 1]["device_id"].nunique()
    print(f"Generated {len(df):,} readings across {df['device_id'].nunique()} assets.")
    print(f"  assets entering failure within the window : {n_fail_assets}")
    print(f"  readings labelled will_fail_72h=1         : {int(df['will_fail_72h'].sum()):,}")
    mix = df[df["failing_component"] != ""]["failing_component"].value_counts()
    print("  readings inside a failure ramp, by component:")
    for k, v in mix.items():
        print(f"      {k:16s} {v:6,}")
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

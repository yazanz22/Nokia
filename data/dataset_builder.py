"""Generator for ``dataset1.csv`` — the synthetic giga-project asset telemetry
dataset used to seed the fleet, back the Network-as-Code mock, and train the ML
fault model.

Each row is an independent labelled reading (not a time series). 500 assets, ~100km
box around 27.5N / 35.0E (NEOM / Gulf of Aqaba). Four labels with distinct signal
signatures:

    NORMAL          reachable, age 0-29s,  signal -70..-50, neighbours 0
    NETWORK_OUTAGE  unreachable, age 5-60m, signal -130..-115, neighbours 3-14
    DEVICE_FAILURE  unreachable, age 10-120m, signal -60..-41 (FINE), neighbours 0, engine 105-129C
    SENSOR_FAILURE  reachable, age 0-59s,  signal -70..-50, neighbours 0   (overlaps NORMAL by design)

NOTE: NORMAL and SENSOR_FAILURE overlap for age < 30 — this is intentional, it
keeps the ML task honest (a perfectly separable set would make the model
meaningless).

The committed ``data/dataset1.csv`` is the canonical copy everything is built and
tested against. This script refuses to overwrite it; pass ``--out`` to write
elsewhere, or delete the file first to regenerate.

    python data/dataset_builder.py --out data/dataset1.new.csv --seed 42
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_LAT, BASE_LON = 27.5, 35.0


def generate(n_samples: int = 15000, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    random.seed(seed)

    device_ids = [f"EQ-{i:04d}" for i in range(1, 501)]
    rows = []

    for _ in range(n_samples):
        device = random.choice(device_ids)
        lat = BASE_LAT + np.random.normal(0, 0.3)
        lon = BASE_LON + np.random.normal(0, 0.3)

        r = np.random.random()
        if r < 0.60:  # NORMAL
            reason, reachable = "NORMAL", True
            age = np.random.randint(0, 30)
            signal = np.random.randint(-70, -50)
            neighbor_fail = 0
        elif r < 0.75:  # NETWORK_OUTAGE — dead zone / tower down
            reason, reachable = "NETWORK_OUTAGE", False
            age = np.random.randint(300, 3600)
            signal = np.random.randint(-130, -115)
            neighbor_fail = np.random.randint(3, 15)
        elif r < 0.90:  # DEVICE_FAILURE — engine / hydraulics died, radio fine
            reason, reachable = "DEVICE_FAILURE", False
            age = np.random.randint(600, 7200)
            signal = np.random.randint(-60, -40)
            neighbor_fail = 0
        else:  # SENSOR_FAILURE — sensor broke, device still pings
            reason, reachable = "SENSOR_FAILURE", True
            age = np.random.randint(0, 60)
            signal = np.random.randint(-70, -50)
            neighbor_fail = 0

        engine_temp = (
            np.random.randint(105, 130)
            if reason == "DEVICE_FAILURE"
            else np.random.randint(70, 95)
        )

        rows.append(
            {
                "timestamp": datetime.now() - timedelta(minutes=int(np.random.randint(0, 1440))),
                "device_id": device,
                "latitude": lat,
                "longitude": lon,
                "reachable": reachable,
                "telemetry_age_sec": age,
                "signal_strength_dbm": signal,
                "neighbor_fail_count": neighbor_fail,
                "engine_temp_c": engine_temp,
                "failure_reason": reason,
            }
        )

    df = pd.DataFrame(rows)
    print(f"Generated {n_samples} samples. Label distribution:\n{df['failure_reason'].value_counts()}")
    return df


def main() -> None:
    default_out = Path(__file__).resolve().parent / "dataset1.csv"
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--n", type=int, default=15000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.out == default_out and args.out.exists():
        raise SystemExit(
            f"refusing to overwrite the canonical {args.out.name}; "
            "pass --out <path> or delete it first"
        )

    df = generate(args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

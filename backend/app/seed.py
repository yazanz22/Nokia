"""Seed data derived from ``data/dataset1.csv``.

The CSV holds 15k labelled telemetry readings across 500 assets (EQ-0001..EQ-0500)
in the NEOM / Gulf of Aqaba region. We use it three ways:

* build the demo fleet of :class:`Asset` objects (id, kind, position),
* give the telemetry simulator a per-asset pool of real readings by label,
* back the mock Network-as-Code adapter (reachable / lat / lon per reading).
"""

from __future__ import annotations

import csv
import functools
import hashlib
import random
from collections import defaultdict
from typing import Any

from .config import DATASET_PATH, get_settings
from .models import Asset, AssetKind, Technician

LABELS = ("NORMAL", "NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE")

_KINDS: list[AssetKind] = ["excavator", "dozer", "haul_truck", "crane", "grader", "loader"]
_KIND_PREFIX = {
    "excavator": "EX",
    "dozer": "DZ",
    "haul_truck": "HT",
    "crane": "CR",
    "grader": "GR",
    "loader": "LD",
}
_SITES = [
    "NEOM — The Line, Sector 3",
    "NEOM — Oxagon Port Works",
    "NEOM — Trojena Ridge",
    "Red Sea Global — Coastal Access Road",
    "NEOM — Hidden Marina Cut",
]

# What each failing component needs on the truck.
COMPONENT_PARTS: dict[str, tuple[str, int]] = {
    "hydraulic_pump": ("HYD-PUMP-40L", 3),
    "cooling_system": ("RADIATOR-CORE-XL", 2),
    "main_bearing": ("BEARING-SET-90", 4),
    "alternator": ("ALTERNATOR-24V", 1),
}

# Fallback by fault mode, for when the component model has nothing to go on. A
# sensor fault needs no component diagnosis — the sensor is the fault — and a
# hardware fault we cannot pin down still gets the commonest part rather than
# an empty work order.
PARTS_CATALOGUE: dict[str, tuple[str, int]] = {
    "DEVICE_FAILURE": ("HYD-PUMP-40L", 3),
    "SENSOR_FAILURE": ("TELEMETRY-SENSOR-KIT", 1),
    "NETWORK_OUTAGE": ("", 0),
    "NORMAL": ("", 0),
}


def _row_to_dict(raw: dict[str, str]) -> dict[str, Any]:
    return {
        "timestamp": raw["timestamp"],
        "device_id": raw["device_id"],
        "latitude": float(raw["latitude"]),
        "longitude": float(raw["longitude"]),
        "reachable": raw["reachable"].strip().lower() == "true",
        "telemetry_age_sec": float(raw["telemetry_age_sec"]),
        "signal_strength_dbm": float(raw["signal_strength_dbm"]),
        "neighbor_fail_count": int(float(raw["neighbor_fail_count"])),
        "engine_temp_c": float(raw["engine_temp_c"]),
        "failure_reason": raw["failure_reason"].strip(),
    }


@functools.lru_cache(maxsize=1)
def load_rows() -> tuple[dict[str, Any], ...]:
    """All dataset rows, parsed, ordered by timestamp."""
    with DATASET_PATH.open(newline="", encoding="utf-8") as fh:
        rows = [_row_to_dict(r) for r in csv.DictReader(fh)]
    rows.sort(key=lambda r: r["timestamp"])
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def asset_pool() -> dict[str, dict[str, list[dict[str, Any]]]]:
    """{asset_id: {label: [rows]}} for every asset in the dataset."""
    pool: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {label: [] for label in LABELS}
    )
    for row in load_rows():
        pool[row["device_id"]][row["failure_reason"]].append(row)
    return {k: v for k, v in pool.items()}


def _stable_int(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest(), 16)


def _asset_from_id(asset_id: str) -> Asset:
    pool = asset_pool()[asset_id]
    # Current position = latest NORMAL reading if any, else latest of anything.
    normal = pool["NORMAL"]
    ref = (normal or [r for rs in pool.values() for r in rs])[-1]
    kind = _KINDS[_stable_int(asset_id) % len(_KINDS)]
    num = asset_id.split("-")[-1].lstrip("0") or "0"
    site = _SITES[_stable_int(asset_id + "site") % len(_SITES)]
    return Asset(
        id=asset_id,
        kind=kind,
        label=f"{kind.replace('_', ' ').title()} {_KIND_PREFIX[kind]}-{int(num):02d}",
        site=site,
        latitude=ref["latitude"],
        longitude=ref["longitude"],
    )


def build_demo_fleet(size: int | None = None) -> list[Asset]:
    """A deterministic subset of assets that can run *both* demo scenarios.

    We only keep assets that have at least one NETWORK_OUTAGE row and at least
    one DEVICE_FAILURE row, so the scenario panel can trigger either on any of
    them.
    """
    size = size or get_settings().demo_fleet_size
    pool = asset_pool()
    eligible = sorted(
        aid
        for aid, by_label in pool.items()
        if by_label["NETWORK_OUTAGE"] and by_label["DEVICE_FAILURE"] and by_label["NORMAL"]
    )
    rng = random.Random(42)
    rng.shuffle(eligible)
    chosen = sorted(eligible[:size])
    return [_asset_from_id(aid) for aid in chosen]


def build_technicians() -> list[Technician]:
    """Six technicians spread across the site, collectively covering every part."""
    rng = random.Random(7)
    # Bounding box of the demo fleet, padded slightly.
    fleet = build_demo_fleet()
    lats = [a.latitude for a in fleet]
    lons = [a.longitude for a in fleet]
    lat_lo, lat_hi = min(lats), max(lats)
    lon_lo, lon_hi = min(lons), max(lons)
    all_parts = [p for p, _ in COMPONENT_PARTS.values()]
    names = [
        "Ziad Khalifeh",
        "Mariam Haddad",
        "Youssef Nasser",
        "Sara Al-Balushi",
        "Omar Farouk",
        "Lina Karam",
    ]
    techs: list[Technician] = []
    for i, name in enumerate(names):
        techs.append(
            Technician(
                id=f"TECH-{i + 1:02d}",
                name=name,
                latitude=rng.uniform(lat_lo, lat_hi),
                longitude=rng.uniform(lon_lo, lon_hi),
                available=True,
                # Everyone carries the sensor kit. The four component parts are split
                # across six people, so two carry a second one — which is why "nearest"
                # and "nearest who can actually fix it" are different questions.
                parts_on_hand=sorted(
                    {all_parts[i % len(all_parts)],
                     all_parts[(i + 2) % len(all_parts)] if i >= len(all_parts) else
                     all_parts[i % len(all_parts)],
                     "TELEMETRY-SENSOR-KIT"}
                ),
            )
        )
    return techs

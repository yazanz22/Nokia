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
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .config import DATASET_PATH, HISTORY_PATH, get_settings
from .models import Asset, AssetKind, Technician

# ── The model contracts live on the training side ───────────────────────────
#
# ``ml/features.py`` declares the fault classes, the component list and the diagnostic
# column order, because those are what ``ml/train.py`` fits the shipped pickles
# against. Anything the backend re-typed from them would be a second opinion about the
# same contract, and the model is the last thing that would complain about a
# disagreement — it does not fail on a wrong column order, it answers confidently and
# wrongly. So they are imported, never restated.
#
# Loaded by path rather than as a package: ``ml/`` is not one (no ``__init__.py``, not
# on the backend's import path) and has to stay runnable on its own as
# ``python ml/train.py``. ``backend/app/ml/forecast.py`` reaches it the same way and
# for the same reason; its loader cannot be reused from here, because ``app.ml``'s
# package init imports ``app.ml.client``, which imports this module — asking
# ``app.ml.forecast`` for the loader would close that ring during startup.
_ML_DIR = Path(__file__).resolve().parents[2] / "ml"


@functools.lru_cache(maxsize=1)
def load_features_module():
    """``ml/features.py`` — the one declaration of every model input contract.

    Public because ``app.ml.client`` needs the same module object and must not open
    a second route to it: two loaders would be two chances to end up looking at two
    different files.
    """
    if str(_ML_DIR) not in sys.path:
        sys.path.insert(0, str(_ML_DIR))
    import features  # type: ignore

    return features


_features = load_features_module()

# The four fault-mode labels, in the order ml/train.py fitted them.
LABELS = tuple(_features.DIAGNOSTIC_CLASSES)

# See models.AssetKind for why these are unattended plant rather than crewed
# machines. The prefix is what shows on the map and the work order.
_KINDS: list[AssetKind] = [
    "generator", "pump_set", "air_compressor", "light_tower", "power_pack", "welder_set"
]
_KIND_PREFIX = {
    "generator": "GN",
    "pump_set": "PS",
    "air_compressor": "AC",
    "light_tower": "LT",
    "power_pack": "HP",
    "welder_set": "WS",
}
# ── The five site working areas ─────────────────────────────────────────────
#
# A working area is a PLACE, so a machine belongs to one because of where it is
# parked — not because of how its name hashes. Sites used to be handed out by
# ``stable_int(asset_id + "site") % 5``, which scattered every site across the whole
# 80 km perimeter. The dashboard draws each site as the convex hull of its machines,
# so five interleaved sets of points produced five hulls that all covered the map and
# all lay on top of each other: the largest feature on the map asserted a spatial
# structure that did not exist.
#
# So the areas are placed first, as fixed points inside the perimeter, and each asset
# joins whichever one it is nearest to. That is a Voronoi partition, and Voronoi cells
# are convex and disjoint — which is exactly the property the map needs, because the
# convex hull of the points inside a convex cell stays inside that cell. Non-overlapping
# hulls fall out of the assignment rule rather than being patched up in the renderer.
#
# The centres sit where the fleet actually is (they were fitted to the demo fleet's
# positions and then rounded), so all five areas hold machines and none of them is a
# label floating over empty desert. Distances are measured in kilometres, not raw
# degrees: a degree of longitude is only 0.887 of a degree of latitude here, and
# assigning on degrees would shear every boundary east-west.
#
# On the naming: the demo puts two of these names on camera — EQ-0295 is
# introduced as Red Sea Global / Coastal Access Road and EQ-0180 as NEOM / Trojena
# Ridge — so the names are bound to the areas those two machines stand in. The
# coordinates in dataset1.csv are synthetic and centred offshore of the real NEOM
# footprint, so there is no true bearing for any of these names to respect anyway;
# what matters is that a name now denotes one compact region instead of a fifth of
# the whole site. Moving a centre may rename a scripted machine's site — check
# EQ-0295 and EQ-0180 against the script before you do.
_SITE_AREAS: tuple[tuple[str, float, float], ...] = (
    ("NEOM — The Line, Sector 3", 27.53, 35.46),
    ("NEOM — Oxagon Port Works", 27.73, 34.58),
    ("NEOM — Trojena Ridge", 27.28, 34.78),
    ("Red Sea Global — Coastal Access Road", 27.61, 35.06),
    ("NEOM — Hidden Marina Cut", 27.11, 35.11),
)

_SITES = [name for name, _, _ in _SITE_AREAS]

# Kilometres per degree at the latitude of the site, for the nearest-centre test.
# The latitude is ``nac.base.SITE_CENTER[0]``, written out rather than imported: a
# module-level ``from .nac.base import ...`` runs ``app.nac``'s package init, which
# pulls in the mock client, which imports this module (see ``_starts_on_site``, which
# imports it inside the function for exactly that reason). It only sets the east-west
# scale of the Voronoi metric, so it is insensitive to a few hundredths of a degree —
# but backend/tests/test_no_duplicate_contracts.py pins it to SITE_CENTER anyway.
_SITE_LATITUDE = 27.5581
_KM_PER_LAT = 111.32
_KM_PER_LON = 111.32 * math.cos(math.radians(_SITE_LATITUDE))


def site_for(latitude: float, longitude: float) -> str:
    """Which working area a position falls in — the nearest of ``_SITE_AREAS``.

    Flat-earth distance on purpose: over an 80 km site the great-circle correction is
    far below the metre, and a plain Euclidean metric in kilometres is what makes the
    partition Voronoi (and therefore the hulls on the map disjoint).
    """
    return min(
        _SITE_AREAS,
        key=lambda area: (
            ((longitude - area[2]) * _KM_PER_LON) ** 2
            + ((latitude - area[1]) * _KM_PER_LAT) ** 2
        ),
    )[0]

# What each failing component needs on the truck. Its keys ARE the component model's
# label set — ``ml/features.py`` derives ``COMPONENT_CLASSES`` from this very dict and
# ``ml/train.py`` fits against that — so the mapping is declared there and imported
# here. A part keyed on a name the model can never emit is a work order that never
# gets written, and nothing would raise: ``client.py`` simply falls through its
# ``if component in COMPONENT_PARTS`` and dispatches the generic kit instead.
COMPONENT_PARTS: dict[str, tuple[str, int]] = _features.COMPONENT_PARTS


# ── What a depot stocks, and what rides in the van ──────────────────────────
#
# Split by whether a technician could plausibly carry it. The four failing components
# are pallet-scale: a 40 L/min hydraulic pump and an XL radiator core are forklift
# items, not something six people each keep a spare of in a pickup. They live on a
# depot shelf. The sensor kit and the service consumables are boxes, and they ride in
# the van — which is why a failed reporting sensor still dispatches direct with no
# detour, and a failed pump does not.
VAN_STOCK: tuple[str, ...] = ("TELEMETRY-SENSOR-KIT",)

# The scheduled-service kit. Preventive work draws exactly this, one per service, and
# it is stocked like anything else so a routine job can be blocked by an empty shelf
# in the same way an emergency one can.
SERVICE_KIT_PART = "SERVICE-KIT-500"

PART_LABELS: dict[str, str] = {
    "HYD-PUMP-40L": "Hydraulic pump, 40 L/min",
    "RADIATOR-CORE-XL": "Radiator core, XL",
    "BEARING-SET-90": "Main bearing set, 90 mm",
    "ALTERNATOR-24V": "Alternator, 24 V",
    "TELEMETRY-SENSOR-KIT": "Telemetry sensor kit",
    SERVICE_KIT_PART: "500-hour service kit",
}

# Reorder point per SKU — the level at or below which the inventory view calls it low.
# Heavy components sit at 1 because a depot holding its last one is a depot that
# cannot cover a second failure; consumables turn over fast enough to warrant more.
PART_REORDER_AT: dict[str, int] = {
    "HYD-PUMP-40L": 1,
    "RADIATOR-CORE-XL": 1,
    "BEARING-SET-90": 1,
    "ALTERNATOR-24V": 1,
    SERVICE_KIT_PART: 4,
}


def build_warehouses() -> list["Warehouse"]:
    """Two parts depots, sited where they shorten the depot-to-machine leg most.

    Not chosen by eye. Taking the five working areas as candidate sites and scoring
    every pair by the mean distance from a fleet machine to its nearer depot, Trojena
    Ridge + Coastal Access wins at 29.2 km against 33.8 km for the next plausible
    pairing. That second leg is driven on every heavy-component job, so it is the one
    worth minimising.

    The stock split is deliberate and load-bearing for the routing. Coastal Access is
    the main store and carries everything; Trojena is a forward store that does not
    hold an alternator at all. So an alternator failure at Trojena — which is exactly
    the demo's hardware scenario — cannot be served by the depot next door, and the
    dispatch has to reason about which technician can collect one and still arrive
    first. With both depots holding one of everything, the pickup would add a constant
    to every journey and never change who goes.
    """
    from .models import Warehouse

    return [
        Warehouse(
            id="WH-01",
            name="Coastal Access Depot",
            # Offset from the working area's own centre rather than sitting on it.
            # A depot is a yard beside the works, not the middle of them, and on the
            # map a marker at the centroid puts its label on top of the area label.
            latitude=27.655,
            longitude=35.118,
            stock={
                "HYD-PUMP-40L": 2,
                "RADIATOR-CORE-XL": 2,
                "BEARING-SET-90": 3,
                "ALTERNATOR-24V": 2,
                SERVICE_KIT_PART: 12,
            },
        ),
        Warehouse(
            id="WH-02",
            name="Trojena Ridge Depot",
            latitude=27.327,
            longitude=34.733,
            stock={
                "HYD-PUMP-40L": 1,
                "BEARING-SET-90": 2,
                # No alternator and no radiator core on this shelf. Absent rather than
                # zero: this forward store does not carry them, which is a different
                # thing from having run out.
                SERVICE_KIT_PART: 6,
            },
        ),
    ]

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


# ── Which assets the prognostic model has never seen ────────────────────────
#
# ``ml/train.py`` splits BY ASSET, holding out the first 25% of the id list after
# shuffling it with numpy's ``default_rng(42)``. The demo fleet used to be drawn
# from all 500 assets with no regard for that line, and 21 of the 30 landed on the
# training side — so the Fleet Health panel a judge looks at was mostly the model
# scoring machines it had been fitted on. The predictions were real but in-sample,
# which is the one thing that turns a good predictive panel into a bad question.
# Seed from the held-out side instead and every forecast on screen is out-of-sample.
#
# Reproduced here rather than imported because backend/ does not import ml/ at
# runtime (only the pickles and features.py). This must stay in lockstep with
# ``ml/train.py::_split_assets`` — same seed, same fraction, same sorted-then-
# shuffled ordering — or it silently reproduces a *different* partition, which
# would look fixed while being no better than the bug it replaces.
_SPLIT_SEED = 42
_TEST_FRAC = 0.25


@functools.lru_cache(maxsize=1)
def _prognostic_test_assets() -> frozenset[str]:
    """Asset ids the prognostic model was NOT trained on."""
    ids: set[str] = set()
    # The split universe is the history CSV's assets, because that is what the
    # prognostic model was fitted on. dataset1.csv covers the identical
    # EQ-0001..EQ-0500 set, so it is a safe fallback on a deploy that ships without
    # the history file (predictive maintenance is already disabled in that case).
    if HISTORY_PATH.exists():
        with HISTORY_PATH.open(newline="", encoding="utf-8") as fh:
            ids = {r["device_id"] for r in csv.DictReader(fh)}
    if not ids:
        ids = set(asset_pool())

    rng = np.random.default_rng(_SPLIT_SEED)
    uniq = sorted(ids)
    rng.shuffle(uniq)
    return frozenset(uniq[: int(len(uniq) * _TEST_FRAC)])


# The demo script names these machines by id and quotes their numbers on camera.
# EQ-0180 (scripted hardware fault → alternator → whoever is nearest carrying one;
# crew are boxed by the fleet bbox, so that name moves when the fleet does) and EQ-0295
# (scripted cellular blindspot) fall on the *training* side of the split above, so
# they are pinned rather than drawn: rewriting the script around two different
# machines costs more than two in-sample rows in a fleet of thirty, and EQ-0295's
# beat never reaches the prognostic model at all. EQ-0051 and EQ-0248 are already
# held out; they are pinned so a reshuffle cannot quietly drop them from the fleet.
_SCRIPTED_ASSETS = ("EQ-0051", "EQ-0180", "EQ-0248", "EQ-0295")

# How far inside the site perimeter a drawn asset has to start — see _starts_on_site.
_PERIMETER_MARGIN_KM = 5.0


def stable_int(key: str) -> int:
    """A hash of ``key`` that is the same in every process.

    Python salts ``hash()`` of str/bytes per interpreter (PYTHONHASHSEED), so
    anything seeded from it silently changes on every restart. Anywhere the demo
    claims to come up the same way twice, seed from this instead. Public because
    the simulator's per-asset samplers seed from it too.
    """
    return int(hashlib.md5(key.encode()).hexdigest(), 16)


# Hours between scheduled services. 500 is the common major-service interval on
# heavy plant, and it is the one figure here a fleet would override per machine class
# — kept as a single constant because the demo fleet is mixed and nothing downstream
# depends on it varying.
_SERVICE_INTERVAL_HOURS = 500.0


def _asset_from_id(asset_id: str) -> Asset:
    pool = asset_pool()[asset_id]
    # Current position = latest NORMAL reading if any, else latest of anything.
    normal = pool["NORMAL"]
    ref = (normal or [r for rs in pool.values() for r in rs])[-1]
    # Namespaced, like the service clock below. Bare stable_int(asset_id) is also
    # what seeds the simulator's per-asset sampler (simulator/profiles.py), so
    # deriving the kind from the same stream tied a machine's type to its telemetry
    # RNG and made the two move together - which is how three of the four scripted
    # demo assets ended up the same kind.
    kind = _KINDS[stable_int(asset_id + ":kind") % len(_KINDS)]
    num = asset_id.split("-")[-1].lstrip("0") or "0"
    # ── the service clock ───────────────────────────────────────────────────
    # Hours on the machine and hours since its last service, seeded from the id so a
    # given machine comes up in the same place in its cycle every run — the preventive
    # list has to be stable between a rehearsal and a performance for the same reason
    # the forecast does. Spread across 0..interval+80 rather than 0..interval so a
    # handful of machines start genuinely overdue: a service board on which nothing is
    # ever late is a service board nobody would recognise.
    h = stable_int(asset_id + ":svc")
    interval = _SERVICE_INTERVAL_HOURS
    return Asset(
        id=asset_id,
        kind=kind,
        label=f"{kind.replace('_', ' ').title()} {_KIND_PREFIX[kind]}-{int(num):02d}",
        # Where it stands, not how its name hashes — see _SITE_AREAS.
        site=site_for(ref["latitude"], ref["longitude"]),
        latitude=ref["latitude"],
        longitude=ref["longitude"],
        engine_hours=round(1200 + (h % 84_000) / 10.0, 1),
        service_interval_hours=interval,
        hours_since_service=round((h // 7) % int(interval + 80), 1),
    )


def _starts_on_site(asset_id: str) -> bool:
    """Is this machine inside the site perimeter at t=0?

    The old fleet satisfied this by accident — its furthest machine sat at 74.9 km
    (the current one sits at 73.8 km)
    of the 80 km radius. Restricting the draw to held-out assets changes which
    machines get picked, and the replacements queue up at 78.5, 79.7 and 102.4 km:
    one of them starts outside the perimeter ring before the geofence beat has even
    run. A machine outside the boundary at t=0 has not wandered; it was placed
    badly, and it makes the "crossed the border" alert meaningless.

    The 5 km margin is not padding for its own sake. The simulator random-walks every
    healthy machine by up to ~0.09 km a tick to keep the map alive, and the geofence
    poll runs over the whole fleet every tick — so a machine parked 0.3 km inside the
    ring will eventually wander out on its own and raise a real-looking "left site"
    alert against a machine nobody drove anywhere, mid-demo, on camera — and it is
    counted as a prevented incident, so the KPI moves too. The old fleet happened to
    clear the boundary by 5.1 km; this makes that margin deliberate.
    """
    # Imported inside the function: ``app.nac`` pulls in the mock client, which
    # imports this module, so a top-level import is a cycle at startup.
    from .nac.base import SITE_CENTER, SITE_RADIUS_KM, haversine_km

    a = _asset_from_id(asset_id)
    km = haversine_km(a.latitude, a.longitude, *SITE_CENTER)
    return km < SITE_RADIUS_KM - _PERIMETER_MARGIN_KM


def build_demo_fleet(size: int | None = None) -> list[Asset]:
    """A deterministic subset of assets that can run *both* demo scenarios.

    We only keep assets that have at least one NETWORK_OUTAGE row and at least
    one DEVICE_FAILURE row, so the scenario panel can trigger either on any of
    them — and, of those, only ones the prognostic model never trained on, so the
    Fleet Health panel is showing genuine out-of-sample forecasts. 122 of the 488
    eligible assets are held out, which is far more headroom than a 30-machine
    fleet needs.

    The fleet is *repaired rather than redrawn*. Almost every number the demo quotes
    is fleet-derived — the furthest asset from the perimeter, the crew's placement
    (``build_technicians`` boxes them by the fleet's bounding box), and therefore
    which technician ends up nearest to the scripted breakdown. Reshuffling all
    thirty machines moved the crew and handed the scripted alternator job to a
    different name. So the previous draw is reproduced, the machines it picked that
    were already held out are kept, and only the ones on the training side are
    replaced.
    """
    size = size or get_settings().demo_fleet_size
    pool = asset_pool()
    held_out = _prognostic_test_assets()
    runnable = sorted(
        aid
        for aid, by_label in pool.items()
        if by_label["NETWORK_OUTAGE"] and by_label["DEVICE_FAILURE"] and by_label["NORMAL"]
    )

    # The draw as it stood before the split was taken into account. Its held-out
    # members are the part of the old fleet that was never a problem.
    previous = list(runnable)
    random.Random(42).shuffle(previous)
    keep = [aid for aid in previous[:size] if aid in held_out]

    # Replacements come from the same shuffle restricted to held-out assets, so the
    # order stays deterministic and the fleet keeps its mixed-kind, mixed-site spread.
    replacements = [
        aid
        for aid in previous
        if aid in held_out and aid not in keep and _starts_on_site(aid)
    ]

    pinned = [aid for aid in _SCRIPTED_ASSETS if aid in pool and aid not in keep]
    chosen = keep + pinned
    chosen += [aid for aid in replacements if aid not in chosen][: max(size - len(chosen), 0)]
    return [_asset_from_id(aid) for aid in sorted(chosen)]


def build_technicians() -> list[Technician]:
    """Six technicians spread across the site, each carrying the same van stock."""
    rng = random.Random(7)
    # Bounding box of the demo fleet, padded slightly.
    fleet = build_demo_fleet()
    lats = [a.latitude for a in fleet]
    lons = [a.longitude for a in fleet]
    lat_lo, lat_hi = min(lats), max(lats)
    lon_lo, lon_hi = min(lons), max(lons)
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
                # Everyone carries the same van stock, because that is what a van
                # holds. "Nearest" and "nearest who can actually fix it" used to be
                # different questions because the components were split across the
                # crew; now the components are in depots and the question that
                # separates them is "nearest who can collect the part and still get
                # there first", which is a routing problem rather than a packing one.
                parts_on_hand=list(VAN_STOCK),
            )
        )
    return techs

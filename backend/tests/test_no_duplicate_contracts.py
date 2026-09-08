"""One declaration per contract.

Five pieces of logic used to be written out in two places each — a haversine, a parts
catalogue, a feature list, a site perimeter, a class list. None of them had anything
comparing the copies, so every one of them was a silent failure waiting on an edit to
whichever copy the next person happened to open.

The feature-order test below is the load-bearing one. A scikit-learn classifier handed
its columns in the wrong order does not raise, does not warn, and does not score
obviously badly — it answers confidently and wrongly, and the agent then narrates that
answer into a work order. There is no runtime symptom to notice, which is exactly why
it needs a test.

Every assertion here is an *identity* or an equality against the source of truth, not a
restatement of the values: this file must not become a sixth copy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from app.agent import tools
from app.ml import client
from app.models import FaultPrediction, TelemetrySample
from app.nac import base as nac_base
from app import seed

ROOT = Path(__file__).resolve().parents[2]
FEATURES = seed.load_features_module()


# ── 1. haversine ────────────────────────────────────────────────────────────


def test_dispatch_and_perimeter_measure_with_the_same_haversine():
    """``agent/tools.py`` used to carry a byte-identical copy of ``nac/base.py``'s.

    Identity, not equal answers: two implementations that agree today are the exact
    thing that drifts. Dispatch distance and perimeter distance appear side by side on
    the map, so they have to be the same function.
    """
    assert tools._haversine_km is nac_base.haversine_km


def test_no_second_haversine_implementation_in_the_agent():
    src = (ROOT / "backend" / "app" / "agent" / "tools.py").read_text(encoding="utf-8")
    assert "6371" not in src, "an earth radius in tools.py means the copy came back"


# ── 2. component -> part catalogue ──────────────────────────────────────────


def test_component_parts_is_the_training_side_dict():
    """The keys of this dict *are* the component model's label set.

    ``ml/features.py`` derives ``COMPONENT_CLASSES`` from it and ``ml/train.py`` fits
    against that, so a part keyed on a name the model can never emit is a work order
    that never gets written — and nothing raises, because ``client.py`` just falls
    through its ``if component in COMPONENT_PARTS``.
    """
    assert seed.COMPONENT_PARTS is FEATURES.COMPONENT_PARTS
    assert client.COMPONENT_PARTS is FEATURES.COMPONENT_PARTS
    assert list(FEATURES.COMPONENT_CLASSES) == list(seed.COMPONENT_PARTS)


def test_every_component_part_is_obtainable_on_site():
    """The mapping is only worth having if a dispatch can actually satisfy it.

    Components live on depot shelves now rather than in vans, so the question moved
    from "does anyone carry it" to "can anyone collect it".
    """
    stocked = {
        p
        for wh in seed.build_warehouses()
        for p, units in wh.stock.items()
        if units > 0
    }
    stocked |= set(seed.VAN_STOCK)
    for component, (part, lead_days) in seed.COMPONENT_PARTS.items():
        assert part in stocked, f"no depot stocks {part} for {component}"
        assert lead_days >= 0


# ── 3. the diagnostic feature contract — the dangerous one ──────────────────


def test_client_declares_no_feature_list_of_its_own():
    assert client.FEATURES is FEATURES.DIAGNOSTIC_FEATURES
    assert client.CLASSES is FEATURES.DIAGNOSTIC_CLASSES


def test_what_the_client_feeds_the_model_is_in_declared_order():
    """The assertion that actually protects the model.

    Every channel gets a value that appears nowhere else in the row, so *any*
    permutation of the five columns fails this — not just a changed length. This is
    what a plain ``FEATURES == DIAGNOSTIC_FEATURES`` comparison cannot catch: the two
    lists could agree while ``features_from`` built its row in some other order.
    """
    sample = TelemetrySample(
        asset_id="EQ-0001",
        reachable=True,
        telemetry_age_sec=11.0,
        signal_strength_dbm=-73.0,
        neighbor_fail_count=5,
        engine_temp_c=97.0,
    )
    by_name = {
        "telemetry_age_sec": 11.0,
        "signal_strength_dbm": -73.0,
        "neighbor_fail_count": 5.0,
        "engine_temp_c": 97.0,
        "reachable": 1.0,
    }
    assert set(by_name) == set(FEATURES.DIAGNOSTIC_FEATURES), (
        "this test's fixture no longer covers every declared feature"
    )

    row = client.features_from(sample)
    assert row == [by_name[name] for name in FEATURES.DIAGNOSTIC_FEATURES]


def test_serving_builds_the_same_row_as_training():
    """Training reads CSV dicts, serving holds a ``TelemetrySample``. Same row out."""
    sample = TelemetrySample(
        asset_id="EQ-0002",
        reachable=False,
        telemetry_age_sec=42.5,
        signal_strength_dbm=-118.0,
        neighbor_fail_count=3,
        engine_temp_c=104.0,
    )
    # The string form is what pandas hands the trainer out of dataset1.csv.
    as_csv_row = {
        "telemetry_age_sec": "42.5",
        "signal_strength_dbm": "-118.0",
        "neighbor_fail_count": "3",
        "engine_temp_c": "104.0",
        "reachable": "False",
    }
    assert client.features_from(sample) == FEATURES.diagnostic_features(as_csv_row)


def test_shipped_model_was_trained_on_this_column_order():
    """``ml/metrics.json`` records the order ``model.pkl`` was actually fitted with.

    Re-training with a reordered contract and forgetting to re-train, or the reverse,
    is the real-world shape of this bug — so compare against the artefact, not just
    against the source.
    """
    metrics_path = ROOT / "ml" / "metrics.json"
    if not metrics_path.exists():
        pytest.skip("ml/metrics.json not present — nothing to compare the pickle to")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["diagnostic"]
    assert metrics["features"] == list(FEATURES.DIAGNOSTIC_FEATURES)
    assert metrics["classes"] == list(FEATURES.DIAGNOSTIC_CLASSES)


def test_one_features_module_not_two():
    """``seed`` and ``ml.forecast`` each bootstrap ``ml/features.py`` onto sys.path.

    Two loaders are two chances to end up looking at two different files, which would
    put the repair-gap rule and the feature order back in the same position they were
    in before. They must resolve to one module object.
    """
    from app.ml import forecast

    assert forecast._load_features_module() is FEATURES


# ── 4. the fault-mode class list ────────────────────────────────────────────


def test_every_statement_of_the_fault_classes_agrees():
    """Four places name these four labels; only ``ml/features.py`` declares them."""
    declared = list(FEATURES.DIAGNOSTIC_CLASSES)
    assert list(seed.LABELS) == declared
    assert list(client.CLASSES) == declared
    # The wire contract. Order is not meaningful in a Literal, so compare as a set.
    wire = get_args(FaultPrediction.model_fields["mode"].annotation)
    assert set(wire) == set(declared)
    # Every mode must have a fallback part entry, or predict() falls back to ("", 0)
    # for a mode nobody remembered to catalogue.
    assert set(seed.PARTS_CATALOGUE) == set(declared)


# ── 5. the site perimeter, across the language boundary ─────────────────────

_FLEET_MAP = ROOT / "frontend" / "src" / "components" / "FleetMap.tsx"


def _tsx_const(source: str, name: str) -> str:
    m = re.search(rf"^const {name}(?::[^=]+)?\s*=\s*(.+?);\s*$", source, re.MULTILINE)
    assert m is not None, f"{name} is no longer declared in FleetMap.tsx"
    return m.group(1).strip()


def test_frontend_site_perimeter_matches_the_backend():
    """A browser cannot import Python, so these two numbers are copied on purpose.

    Serving them in the websocket snapshot would turn a fixed geographic constant into
    a runtime dependency — the perimeter ring could not be drawn until the first frame
    landed, and every reader would need a fallback for a value that has never changed.
    The duplication was only dangerous because nothing compared the copies. This does.
    """
    src = _FLEET_MAP.read_text(encoding="utf-8")

    lat, lon = json.loads(_tsx_const(src, "SITE_CENTER"))
    assert (lat, lon) == nac_base.SITE_CENTER

    radius = float(_tsx_const(src, "SITE_RADIUS_KM"))
    assert radius == nac_base.SITE_RADIUS_KM


def test_frontend_names_its_source_of_truth():
    """The comment is the only thing telling the next editor where to change it."""
    src = _FLEET_MAP.read_text(encoding="utf-8")
    assert "backend/app/nac/base.py" in src
    assert "test_no_duplicate_contracts" in src


def test_voronoi_metric_is_scaled_at_the_site_centre():
    """``seed._SITE_LATITUDE`` cannot import SITE_CENTER (it would close an import
    ring through ``app.nac``), so it is written out. Pin it here instead."""
    assert seed._SITE_LATITUDE == nac_base.SITE_CENTER[0]

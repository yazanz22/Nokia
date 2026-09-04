"""Contract tests for the diagnostic client (``app/ml/client.py``).

These deliberately assert *shape and wiring*, not today's numbers. An earlier version
of this file pinned ``recommended_part == "HYD-PUMP-40L"`` for a hardcoded asset id,
which made it a test of two things it never claimed to cover: the exact bytes of
``ml/component_model.pkl`` and the value of ``FORECAST_AS_OF`` (which decides how much
history each asset has, and therefore whether it looks like it is degrading at all).
Retraining the models or moving the as-of instant broke it for reasons unrelated to
the client. Worse, it locked in a bug: at the time, the component model was consulted
for *every* DEVICE_FAILURE, so a perfectly healthy machine got a confidently invented
part number. That is now gated on the prognostic model's ``at_risk``, and both sides
of that gate are asserted below.

So where a test needs a particular machine it *finds* one by the property it is about
to assert — "an asset the forecaster scores at_risk" — and skips with a reason if the
fleet contains none, rather than naming an id that is only correct on one as-of date.
"""

from __future__ import annotations

import pytest

from app.ml.client import CLASSES, FEATURES, FaultModel, fault_model, features_from
from app.models import FaultPrediction, TelemetrySample
from app.seed import COMPONENT_PARTS, PARTS_CATALOGUE


def _s(**kw) -> TelemetrySample:
    base = dict(
        asset_id="EQ-0001",
        reachable=True,
        telemetry_age_sec=10,
        signal_strength_dbm=-60,
        neighbor_fail_count=0,
        engine_temp_c=82,
    )
    base.update(kw)
    return TelemetrySample(**base)


# The four archetypes the classifier exists to separate, as (name, sample, mode).
ARCHETYPES = [
    ("normal", _s(), "NORMAL"),
    # unreachable, hot engine, strong signal, no neighbour failures
    ("device_failure", _s(reachable=False, engine_temp_c=120, signal_strength_dbm=-48), "DEVICE_FAILURE"),
    (
        "network_outage",
        _s(reachable=False, signal_strength_dbm=-124, neighbor_fail_count=8, engine_temp_c=85),
        "NETWORK_OUTAGE",
    ),
    ("sensor_failure", _s(telemetry_age_sec=45), "SENSOR_FAILURE"),
]

DEVICE_FAILURE_SAMPLE = ARCHETYPES[1][1]


def _rule_model() -> FaultModel:
    """A FaultModel forced onto the rule-based path, without touching the global one."""
    rules = FaultModel.__new__(FaultModel)
    rules._model = None
    return rules


def _models() -> list[FaultModel]:
    """Both backends when a pickle is present, otherwise just the rule path."""
    out = [_rule_model()]
    if fault_model.backend == "trained":
        out.append(fault_model)
    return out


def _first_asset(want_at_risk: bool) -> str:
    """An asset id the forecaster does / does not see a degradation trend on.

    Chosen by the property under test rather than hardcoded, so the test survives a
    retrain and a change to FORECAST_AS_OF.
    """
    from app.ml.forecast import _history, forecast_model

    for asset_id in sorted(_history()):
        score = forecast_model.score_asset(asset_id)
        gate_open = score is not None and bool(score.get("at_risk"))
        if gate_open is want_at_risk:
            return asset_id
    pytest.skip(
        f"no asset in the replayed history is {'at risk' if want_at_risk else 'trend-free'} "
        "at the configured FORECAST_AS_OF — nothing to assert the component gate against"
    )


# ── the feature vector is the input contract ────────────────────────────────


def test_feature_vector_matches_training_column_order():
    """``features_from`` must build the columns ml/train.py fitted on, in that order.

    Column order is silent when it is wrong: a transposed pair still produces a
    confident prediction, just of the wrong thing. So compare against the training-time
    builder itself, on a sample whose channels are all distinct values — any
    permutation changes the vector.
    """
    from app.ml.forecast import _load_features_module

    feats = _load_features_module()
    assert FEATURES == feats.DIAGNOSTIC_FEATURES
    assert set(CLASSES) == set(feats.DIAGNOSTIC_CLASSES)

    sample = _s(
        telemetry_age_sec=41.0,
        signal_strength_dbm=-97.0,
        neighbor_fail_count=3,
        engine_temp_c=113.0,
        reachable=False,
    )
    built = features_from(sample)
    reference = feats.diagnostic_features(
        {name: getattr(sample, name) for name in FEATURES}
    )
    assert built == reference
    # distinct values, so the equality above is actually order-sensitive
    assert len(set(built)) == len(built)


def test_feature_vector_matches_model_input_width():
    if fault_model.backend != "trained":
        pytest.skip("no ml/model.pkl — nothing to check the vector width against")
    model = fault_model._model
    assert model.n_features_in_ == len(FEATURES)
    assert set(model.classes_) == set(CLASSES)


# ── every prediction is well-formed, whichever backend answered ─────────────


@pytest.mark.parametrize("name,sample,_expected", ARCHETYPES)
def test_prediction_invariants(name, sample, _expected):
    for model in _models():
        p = model.predict("EQ-0001", sample)
        assert isinstance(p, FaultPrediction)
        assert p.asset_id == "EQ-0001"
        assert p.mode in CLASSES
        assert 0.0 <= p.confidence <= 1.0
        assert set(p.probabilities) <= set(CLASSES)
        assert p.probabilities[p.mode] == p.confidence
        assert p.confidence == max(p.probabilities.values())
        assert sum(p.probabilities.values()) == pytest.approx(1.0, abs=0.01)
        assert p.rationale.strip()
        assert 0.0 <= p.component_confidence <= 1.0


@pytest.mark.parametrize("name,sample,expected", ARCHETYPES)
def test_signature_is_classified_as_its_archetype(name, sample, expected):
    """The four signatures the whole closed loop branches on.

    Asserted for both backends: the rule classifier is the fallback the app runs on
    when the pickle is missing, and it has to make the same call.
    """
    for model in _models():
        assert model.predict("EQ-0001", sample).mode == expected, f"{model.backend} on {name}"


def test_rule_and_trained_backends_share_an_interface():
    """Swapping the trained model for the fallback must not break a caller."""
    if fault_model.backend != "trained":
        pytest.skip("no ml/model.pkl — only one backend available to compare")
    for _name, sample, _expected in ARCHETYPES:
        rule = _rule_model().predict("EQ-0001", sample)
        trained = fault_model.predict("EQ-0001", sample)
        assert set(rule.probabilities) == set(trained.probabilities)
        # same fields, same types — a caller cannot tell which one answered
        for field in FaultPrediction.model_fields:
            assert type(getattr(rule, field)) is type(getattr(trained, field)), field


# ── the component gate: named part when there is a trend, fallback when not ─


def test_device_failure_with_trend_names_component_and_matching_part():
    asset_id = _first_asset(want_at_risk=True)
    p = fault_model.predict(asset_id, DEVICE_FAILURE_SAMPLE)
    assert p.mode == "DEVICE_FAILURE"
    assert p.component in COMPONENT_PARTS, p.component
    part, _lead = COMPONENT_PARTS[p.component]
    # The part on the work order has to be the part for the named component — this is
    # the whole point of consulting the component model.
    assert p.recommended_part == part
    assert 0.0 < p.component_confidence <= 1.0
    assert p.component.replace("_", " ") in p.rationale


def test_device_failure_without_trend_names_no_component_but_still_a_part():
    """The gate. No degradation trend means no component — but not an empty van."""
    asset_id = _first_asset(want_at_risk=False)
    p = fault_model.predict(asset_id, DEVICE_FAILURE_SAMPLE)
    assert p.mode == "DEVICE_FAILURE"
    assert p.component == ""
    assert p.component_confidence == 0.0
    fallback, _lead = PARTS_CATALOGUE["DEVICE_FAILURE"]
    assert fallback, "the DEVICE_FAILURE fallback part must not be empty"
    assert p.recommended_part == fallback
    # and the technician is told what they are carrying
    assert p.recommended_part in p.rationale


@pytest.mark.parametrize(
    "name,sample,expected",
    [a for a in ARCHETYPES if a[2] != "DEVICE_FAILURE"],
)
def test_only_device_failure_consults_the_component_model(name, sample, expected):
    """A non-hardware mode never names a component, on any asset."""
    asset_id = _first_asset(want_at_risk=True)
    for model in _models():
        p = model.predict(asset_id, sample)
        assert p.mode == expected
        assert p.component == ""
        assert p.component_confidence == 0.0
        assert p.recommended_part == PARTS_CATALOGUE[expected][0]

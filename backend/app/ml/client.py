"""Fault-classification client used by the agent's ``predict_fault`` tool.

Loads ``ml/model.pkl`` (trained by ``ml/train.py`` on ``data/dataset1.csv``) when
present. Until the model is trained, a transparent rule-based classifier stands in
behind the identical interface so the closed loop is demoable end-to-end from day
one. Both paths return a :class:`FaultPrediction`.
"""

from __future__ import annotations

import logging

from ..config import MODEL_PATH
from ..models import FaultPrediction, TelemetrySample
from ..seed import COMPONENT_PARTS, PARTS_CATALOGUE, load_features_module

log = logging.getLogger("ml")

# The diagnostic contract, taken from the one place it is declared: ``ml/features.py``,
# which is what ``ml/train.py`` fitted ``model.pkl`` against.
#
# Column ORDER is the contract, and it is the dangerous half. A model handed its five
# features in a different order does not raise, does not warn and does not score badly
# enough to notice — it answers confidently and wrongly, and every downstream sentence
# the agent narrates is built on that answer. Re-typing the list here was two
# declarations of one contract with nothing comparing them; now the row this module
# feeds the model is built by the *training-side* builder rather than by a second
# implementation of it.
_features = load_features_module()

FEATURES = _features.DIAGNOSTIC_FEATURES
CLASSES = _features.DIAGNOSTIC_CLASSES

_RATIONALE = {
    "NORMAL": "All monitored channels within nominal bands.",
    "NETWORK_OUTAGE": "Weak serving cell and multiple neighbour-cell failures with a stale uplink — consistent with a coverage gap, not an equipment fault.",
    "DEVICE_FAILURE": "Engine temperature far above the safe envelope while the radio link is healthy — an on-board hardware fault.",
    "SENSOR_FAILURE": "Telemetry age drifting above spec while every physical channel reads normal — the reporting sensor, not the machine.",
}


def _pct(v: float) -> str:
    """Confidence as text, refusing to claim certainty.

    `identify_component` returns values like 0.9999999979, which `round(x, 3)` stores as
    exactly 1.0 — so any decimal place prints "100.0%", which reads as *more* certain
    rather than less. A model that claims 100% invites a challenge it cannot win, and
    the component model in particular has no null class to be certain against. State the
    magnitude, not a certainty.
    """
    return ">99%" if v >= 0.995 else f"{v:.0%}"


def features_from(sample: TelemetrySample) -> list[float]:
    """One live reading as a model input row, in ``FEATURES`` order.

    The row is assembled by ``ml/features.py::diagnostic_features`` — the same
    function that built every row the model was trained on — so serving cannot drift
    from training by a reordered column or a differently-coerced boolean. All this
    adds is the shape conversion: training reads CSV dicts, serving holds a
    ``TelemetrySample``.
    """
    return _features.diagnostic_features(sample.model_dump())


class FaultModel:
    def __init__(self) -> None:
        self._model = None
        self._load()

    def _load(self) -> None:
        if not MODEL_PATH.exists():
            log.info("No %s yet — using rule-based fault classifier", MODEL_PATH.name)
            return
        try:
            import joblib

            self._model = joblib.load(MODEL_PATH)
            log.info("Loaded trained fault model from %s", MODEL_PATH)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load %s (%s) — using rule-based classifier", MODEL_PATH, exc)

    @property
    def backend(self) -> str:
        return "trained" if self._model is not None else "rule-based"

    def predict(self, asset_id: str, sample: TelemetrySample) -> FaultPrediction:
        if self._model is not None:
            probs = self._predict_trained(sample)
        else:
            probs = self._predict_rules(sample)
        mode = max(probs, key=probs.get)
        part, _lead = PARTS_CATALOGUE.get(mode, ("", 0))
        component = ""
        comp_conf = 0.0
        rationale = _RATIONALE[mode]

        # A hardware fault is not a part. Ask the machine's own history which
        # component is failing, and let that choose what goes on the truck.
        if mode == "DEVICE_FAILURE":
            from .forecast import forecast_model

            # The component model was trained only on windows already inside a failure
            # ramp — there is no "nothing is wrong" class for it to pick. Asked about a
            # healthy machine it still returns its best guess, and does so at 99%+:
            # measured across ~9,900 healthy test windows the mean top probability is
            # 0.87, and 64% of them come back "hydraulic_pump". Ungated, any machine
            # the demo has not scripted gets a confidently invented part number on its
            # work order.
            #
            # So the prognostic score is the gate. It is the model that *does* have a
            # negative class, and if it cannot see a degradation ramp then there is no
            # ramp for the component model to be reading.
            score = forecast_model.score_asset(asset_id)
            found = (
                forecast_model.identify_component(asset_id)
                if score is not None and score.get("at_risk")
                else None
            )
            if found is None:
                rationale = (
                    f"{rationale} No degradation trend in this machine's recent history, "
                    "so the failing component cannot be named from it — the technician "
                    f"is sent to diagnose on site with a {part or 'standard kit'}."
                )
            else:
                component, comp_conf = found
                if component in COMPONENT_PARTS:
                    part, _lead = COMPONENT_PARTS[component]
                    rationale = (
                        f"{rationale} Recent history points to the "
                        f"{component.replace('_', ' ')} "
                        f"({_pct(comp_conf)} confidence), "
                        f"so the technician needs a {part}."
                    )

        return FaultPrediction(
            asset_id=asset_id,
            mode=mode,  # type: ignore[arg-type]
            confidence=round(probs[mode], 3),
            probabilities={k: round(v, 3) for k, v in probs.items()},
            recommended_part=part,
            component=component,
            component_confidence=round(comp_conf, 3),
            rationale=rationale,
        )

    # ── trained model ───────────────────────────────────────────────────
    def _predict_trained(self, sample: TelemetrySample) -> dict[str, float]:
        import numpy as np

        x = np.array([features_from(sample)], dtype=float)
        proba = self._model.predict_proba(x)[0]
        classes = list(self._model.classes_)
        return {c: float(proba[i]) for i, c in enumerate(classes)}

    # ── rule-based stand-in (mirrors the dataset's generative structure) ─
    def _predict_rules(self, sample: TelemetrySample) -> dict[str, float]:
        probs = {c: 0.02 for c in CLASSES}
        age = sample.telemetry_age_sec
        temp = sample.engine_temp_c
        sig = sample.signal_strength_dbm
        nbr = sample.neighbor_fail_count

        if not sample.reachable:
            if temp >= 100 and sig >= -80 and nbr == 0:
                probs["DEVICE_FAILURE"] = 0.92
            elif sig <= -105 or nbr >= 2:
                probs["NETWORK_OUTAGE"] = 0.9
            else:
                probs["DEVICE_FAILURE"] = 0.55
                probs["NETWORK_OUTAGE"] = 0.4
        else:
            if temp >= 100:
                probs["DEVICE_FAILURE"] = 0.85
            elif age >= 30:
                probs["SENSOR_FAILURE"] = 0.88
            else:
                probs["NORMAL"] = 0.9

        total = sum(probs.values())
        return {k: v / total for k, v in probs.items()}


fault_model = FaultModel()


def warm_up() -> None:
    """Pay the first-inference cost before the demo starts, not during it.

    A DEVICE_FAILURE prediction reaches into ``forecast`` for the failing component,
    and that path is lazy on purpose: it imports the shared feature module and parses
    the whole 4.3 MB / 33k-row telemetry history on first use. Warm that is ~70 ms;
    cold it is ~2 s, and unless something has already hit ``/api/fleet/health`` the
    cold hit lands on the first live incident — the one being narrated on stage.

    So we do the same work up front against a real asset id, which populates the
    ``lru_cache`` on the history and puts ``features`` in ``sys.modules``. Called from
    the app lifespan in a worker thread; it is pure cache-filling, so a failure here
    costs nothing but a slow first prediction and must never take startup with it.
    """
    from .forecast import _history, _load_features_module, forecast_model

    _load_features_module()
    history = _history()
    if history:
        # Any asset will do — one real score exercises the whole predict path
        # (feature build, model, component head) rather than just the file read.
        forecast_model.score_asset(next(iter(history)))
    log.info("ML warm-up complete — %d assets of history cached", len(history))

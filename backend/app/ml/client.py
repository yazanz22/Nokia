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
from ..seed import COMPONENT_PARTS, PARTS_CATALOGUE

log = logging.getLogger("ml")

# Feature order shared with ml/train.py
FEATURES = [
    "telemetry_age_sec",
    "signal_strength_dbm",
    "neighbor_fail_count",
    "engine_temp_c",
    "reachable",
]
CLASSES = ["NORMAL", "NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE"]

_RATIONALE = {
    "NORMAL": "All monitored channels within nominal bands.",
    "NETWORK_OUTAGE": "Weak serving cell and multiple neighbour-cell failures with a stale uplink — consistent with a coverage gap, not an equipment fault.",
    "DEVICE_FAILURE": "Engine temperature far above the safe envelope while the radio link is healthy — an on-board hardware fault.",
    "SENSOR_FAILURE": "Telemetry age drifting above spec while every physical channel reads normal — the reporting sensor, not the machine.",
}


def features_from(sample: TelemetrySample) -> list[float]:
    return [
        float(sample.telemetry_age_sec),
        float(sample.signal_strength_dbm),
        float(sample.neighbor_fail_count),
        float(sample.engine_temp_c),
        1.0 if sample.reachable else 0.0,
    ]


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
        part, lead = PARTS_CATALOGUE.get(mode, ("", 0))
        component = ""
        comp_conf = 0.0
        rationale = _RATIONALE[mode]

        # A hardware fault is not a part. Ask the machine's own history which
        # component is failing, and let that choose what goes on the truck.
        if mode == "DEVICE_FAILURE":
            from .forecast import forecast_model

            found = forecast_model.identify_component(asset_id)
            if found is not None:
                component, comp_conf = found
                if component in COMPONENT_PARTS:
                    part, lead = COMPONENT_PARTS[component]
                    rationale = (
                        f"{rationale} Recent history points to the "
                        f"{component.replace('_', ' ')} ({comp_conf:.0%} confidence), "
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
            lead_days=lead,
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

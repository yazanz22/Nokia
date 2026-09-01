"""Predictive maintenance — which machines are heading for failure.

This is the counterpart to ``client.py``. That one is reactive: a machine has gone
silent, work out what broke. This one is proactive: nothing has gone wrong yet, but
the trend says something will.

It scores each fleet asset against a trailing window of its telemetry history and
answers with the tightest horizon the model is confident about, so the dashboard can
say "≈2 days" rather than just "at risk". The horizon comes from asking the model the
same question at 24/48/72h — never from the label.
"""

from __future__ import annotations

import csv
import functools
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import FORECAST_MODEL_PATH, HISTORY_PATH, get_settings

log = logging.getLogger("ml.forecast")

# Feature builder lives in ml/ and is shared with training — see ml/features.py.
_ML_DIR = Path(__file__).resolve().parents[3] / "ml"

RISK_THRESHOLD = 0.5


def _load_features_module():
    import sys

    if str(_ML_DIR) not in sys.path:
        sys.path.insert(0, str(_ML_DIR))
    import features  # type: ignore

    return features


@functools.lru_cache(maxsize=1)
def _history() -> dict[str, list[dict[str, Any]]]:
    """{asset_id: [readings]} up to the configured as-of instant, oldest first."""
    if not HISTORY_PATH.exists():
        log.warning("no %s — predictive maintenance disabled", HISTORY_PATH.name)
        return {}
    as_of = get_settings().forecast_as_of
    cutoff = datetime.fromisoformat(as_of) if as_of else None

    by_asset: dict[str, list[dict[str, Any]]] = {}
    with HISTORY_PATH.open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            ts = datetime.fromisoformat(raw["timestamp"])
            if cutoff and ts > cutoff:
                continue
            by_asset.setdefault(raw["device_id"], []).append(
                {
                    "timestamp": ts,
                    "engine_hours": float(raw["engine_hours"]),
                    "vibration_mm_s": float(raw["vibration_mm_s"]),
                    "oil_particle_count": float(raw["oil_particle_count"]),
                    "hydraulic_pressure_bar": float(raw["hydraulic_pressure_bar"]),
                    "engine_temp_c": float(raw["engine_temp_c"]),
                }
            )
    for rows in by_asset.values():
        rows.sort(key=lambda r: r["timestamp"])
    return by_asset


class ForecastModel:
    def __init__(self) -> None:
        self._models: dict[float, Any] = {}
        self._horizons: list[float] = []
        self._load()

    def _load(self) -> None:
        if not FORECAST_MODEL_PATH.exists():
            log.info("no %s — run ml/train.py to enable forecasting", FORECAST_MODEL_PATH.name)
            return
        try:
            import joblib

            blob = joblib.load(FORECAST_MODEL_PATH)
            self._models = blob["models"]
            self._horizons = sorted(blob["horizons"])
            log.info("loaded forecast models for horizons %s", self._horizons)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load %s: %s", FORECAST_MODEL_PATH, exc)

    @property
    def available(self) -> bool:
        return bool(self._models) and bool(_history())

    def score_asset(self, asset_id: str) -> dict[str, Any] | None:
        """Risk for one asset, or None if we have no usable history for it."""
        if not self._models:
            return None
        feats = _load_features_module()
        rows = _history().get(asset_id) or []
        if len(rows) < feats.WINDOW:
            return None
        window = rows[-feats.WINDOW :]
        x = [feats.prognostic_features(window)]

        # Probability at each horizon, then the tightest one that clears threshold.
        probs = {h: float(m.predict_proba(x)[0][1]) for h, m in self._models.items()}
        fired = [h for h in self._horizons if probs[h] >= RISK_THRESHOLD]
        horizon = min(fired) if fired else None
        risk = max(probs.values())

        latest = window[-1]
        first = window[0]
        return {
            "asset_id": asset_id,
            "risk": round(risk, 3),
            "horizon_hours": horizon,
            "probabilities": {f"{int(h)}h": round(p, 3) for h, p in sorted(probs.items())},
            "at_risk": horizon is not None,
            # The channels that moved — this is what makes the call explainable.
            "vibration_mm_s": round(latest["vibration_mm_s"], 2),
            "vibration_delta": round(latest["vibration_mm_s"] - first["vibration_mm_s"], 2),
            "oil_particle_count": round(latest["oil_particle_count"], 0),
            "oil_particle_delta": round(
                latest["oil_particle_count"] - first["oil_particle_count"], 0
            ),
            "hydraulic_pressure_bar": round(latest["hydraulic_pressure_bar"], 1),
            "engine_temp_c": round(latest["engine_temp_c"], 1),
            "as_of": latest["timestamp"].isoformat(),
        }

    def score_fleet(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        out = [s for aid in asset_ids if (s := self.score_asset(aid)) is not None]
        out.sort(key=lambda s: (not s["at_risk"], s["horizon_hours"] or 1e9, -s["risk"]))
        return out


forecast_model = ForecastModel()

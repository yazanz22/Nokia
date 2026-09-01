"""Trains the two models the agent calls.

    python ml/train.py

1. **Diagnostic** (``model.pkl``) — from ``data/dataset1.csv``. One reading in,
   "what broke?" out. Four classes.
2. **Prognostic** (``forecast_model.pkl``) — from ``data/telemetry_history.csv``.
   A trailing window of readings in, "will this fail within 72 hours?" out.

The prognostic model is the interesting one, and the headline number is not its
accuracy — it is the **warning time**. We report it against the obvious baseline
(an engine-temperature threshold), because temperature is the last signal to move.
Beating that baseline at long horizons is the entire claim.

Splits are **by asset**, never by row: two readings from the same machine hours
apart are near-duplicates, so a row-wise split would leak and flatter the model.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    f1_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import (  # noqa: E402
    DIAGNOSTIC_CLASSES,
    DIAGNOSTIC_FEATURES,
    PROGNOSTIC_FEATURES,
    WINDOW,
    diagnostic_features,
    prognostic_features,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET1 = ROOT / "data" / "dataset1.csv"
HISTORY = ROOT / "data" / "telemetry_history.csv"
MODEL_OUT = Path(__file__).resolve().parent / "model.pkl"
FORECAST_OUT = Path(__file__).resolve().parent / "forecast_model.pkl"
METRICS_OUT = Path(__file__).resolve().parent / "metrics.json"

SEED = 42
HORIZON_H = 72.0  # "will it fail in the next 3 days?"


def _split_assets(ids: list[str], frac: float = 0.25) -> tuple[set[str], set[str]]:
    rng = np.random.default_rng(SEED)
    uniq = sorted(set(ids))
    rng.shuffle(uniq)
    cut = int(len(uniq) * frac)
    return set(uniq[cut:]), set(uniq[:cut])  # train, test


# ── 1. Diagnostic model ─────────────────────────────────────────────────────


def train_diagnostic() -> dict:
    print("\n" + "=" * 62)
    print("DIAGNOSTIC MODEL  —  what broke?  (data/dataset1.csv)")
    print("=" * 62)
    df = pd.read_csv(DATASET1)
    X = np.array([diagnostic_features(r) for _, r in df.iterrows()], dtype=float)
    y = df["failure_reason"].to_numpy()

    train_ids, test_ids = _split_assets(df["device_id"].tolist())
    tr = df["device_id"].isin(train_ids).to_numpy()
    te = ~tr

    clf = GradientBoostingClassifier(random_state=SEED)
    clf.fit(X[tr], y[tr])
    pred = clf.predict(X[te])

    acc = accuracy_score(y[te], pred)
    macro_f1 = f1_score(y[te], pred, average="macro")
    print(f"\n  train {tr.sum():,} rows / test {te.sum():,} rows (split by asset)")
    print(f"  accuracy  {acc:.3f}")
    print(f"  macro F1  {macro_f1:.3f}")
    print("\n" + classification_report(y[te], pred, digits=3, zero_division=0))

    print("  NOTE: NORMAL and SENSOR_FAILURE overlap by construction below 30s of")
    print("  telemetry age, so SENSOR recall is capped near 0.50. That ceiling is")
    print("  real, not a modelling failure — see data/dataset_builder.py.")

    import joblib

    joblib.dump(clf, MODEL_OUT)
    print(f"\n  wrote {MODEL_OUT.name}")

    return {
        "rows_train": int(tr.sum()),
        "rows_test": int(te.sum()),
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "per_class_f1": {
            c: round(float(f), 4)
            for c, f in zip(
                sorted(set(y)),
                f1_score(y[te], pred, average=None, labels=sorted(set(y)), zero_division=0),
            )
        },
        "features": DIAGNOSTIC_FEATURES,
        "classes": DIAGNOSTIC_CLASSES,
    }


# ── 2. Prognostic model ─────────────────────────────────────────────────────


def _build_windows(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Slide a WINDOW-long window over each asset's history.

    Returns (X, y, asset_ids, hours_to_failure).
    """
    df = df.sort_values(["device_id", "timestamp"])
    X: list[list[float]] = []
    y: list[int] = []
    assets: list[str] = []
    htf: list[float] = []

    for asset_id, g in df.groupby("device_id", sort=False):
        recs = g.to_dict("records")
        for i in range(WINDOW - 1, len(recs)):
            window = recs[i - WINDOW + 1 : i + 1]
            X.append(prognostic_features(window))
            y.append(int(recs[i]["will_fail_72h"]))
            assets.append(asset_id)
            raw = recs[i]["hours_to_failure"]
            htf.append(float(raw) if raw not in ("", None) and not pd.isna(raw) else np.nan)

    return np.array(X, dtype=float), np.array(y), np.array(assets), np.array(htf, dtype=float)


def _temperature_baseline(df: pd.DataFrame, X_assets: np.ndarray) -> np.ndarray:
    """The obvious alternative: flag anything running hot.

    Threshold chosen as the 97.5th percentile of healthy readings, i.e. tuned to be
    as generous as it can be without alarming constantly.
    """
    healthy = df[df["will_fail_72h"] == 0]["engine_temp_c"]
    return np.full(len(X_assets), float(np.percentile(healthy, 97.5)))


def train_prognostic() -> dict:
    print("\n" + "=" * 62)
    print("PROGNOSTIC MODEL  —  what is ABOUT to break?")
    print("                    (data/telemetry_history.csv)")
    print("=" * 62)
    df = pd.read_csv(HISTORY)
    X, y, assets, htf = _build_windows(df)
    print(f"\n  {len(X):,} windows from {len(set(assets))} assets ({y.sum():,} positive)")

    train_ids, test_ids = _split_assets(assets.tolist())
    tr = np.isin(assets, list(train_ids))
    te = ~tr

    # Train one classifier per horizon. A single "fails within 72h" model cannot say
    # *how soon*; asking the same question at 24/48/72h and taking the tightest one
    # that fires gives an honest estimate that comes from the model rather than from
    # the label we are trying to predict.
    horizons = [24.0, 48.0, 72.0]
    models: dict[float, HistGradientBoostingClassifier] = {}
    for h in horizons:
        yh = ((~np.isnan(htf)) & (htf <= h)).astype(int)
        m = HistGradientBoostingClassifier(random_state=SEED, max_iter=300)
        m.fit(X[tr], yh[tr])
        models[h] = m
        te_auc = roc_auc_score(yh[te], m.predict_proba(X[te])[:, 1])
        print(f"  horizon {int(h):>3d}h  positives {int(yh.sum()):>6,}  test ROC AUC {te_auc:.3f}")

    clf = models[HORIZON_H]
    proba = clf.predict_proba(X[te])[:, 1]
    pred = (proba >= 0.5).astype(int)

    auc = roc_auc_score(y[te], proba)
    ap = average_precision_score(y[te], proba)
    print(f"  train {tr.sum():,} windows / test {te.sum():,} (split by asset)")
    print(f"  ROC AUC   {auc:.3f}")
    print(f"  PR  AUC   {ap:.3f}")
    print("\n" + classification_report(y[te], pred, digits=3, zero_division=0))

    # ── the number that actually matters: warning time ──────────────────────
    temp_thresh = _temperature_baseline(df, assets)[0]
    temp_col = list(df.columns).index("engine_temp_c")
    # engine_temp "last" is the 16th prognostic feature (4th channel, 1st stat)
    temp_last_idx = PROGNOSTIC_FEATURES.index("engine_temp_c_last")

    print(f"\n  Warning time — model vs. a temperature threshold ({temp_thresh:.1f} C)")
    print("  " + "-" * 58)
    print(f"  {'hours before failure':>22s}   {'our model':>10s}   {'temp rule':>10s}")

    bands = [(120, 96), (96, 72), (72, 48), (48, 24), (24, 0)]
    detect: dict[str, dict[str, float]] = {}
    for hi, lo in bands:
        m = te & (htf <= hi) & (htf > lo) & ~np.isnan(htf)
        if m.sum() == 0:
            continue
        ours = float((proba[m[te]] >= 0.5).mean()) if m[te].size else 0.0
        # recompute on the test subset properly
        sub = np.isnan(htf) == False  # noqa: E712
        idx = np.where(te & sub & (htf <= hi) & (htf > lo))[0]
        te_idx = np.where(te)[0]
        pos = np.searchsorted(te_idx, idx)
        pos = pos[(pos < len(te_idx))]
        ours = float((proba[pos] >= 0.5).mean()) if len(pos) else 0.0
        temp_hit = float((X[idx, temp_last_idx] >= temp_thresh).mean()) if len(idx) else 0.0
        print(f"  {f'{lo}-{hi}h':>22s}   {ours:>9.0%}   {temp_hit:>10.0%}")
        detect[f"{lo}-{hi}h"] = {
            "model_detection_rate": round(ours, 4),
            "temperature_rule_detection_rate": round(temp_hit, 4),
            "n_windows": int(len(idx)),
        }

    print("\n  Temperature only moves in the final hours, so the rule cannot give")
    print("  more than a shift's notice. Vibration and oil-particle TRENDS move")
    print("  days out — which is the whole reason this needs a model.")

    import joblib

    joblib.dump({"horizons": horizons, "models": models}, FORECAST_OUT)
    print(f"\n  wrote {FORECAST_OUT.name} ({len(models)} horizon models)")

    return {
        "horizons_hours": horizons,
        "windows_train": int(tr.sum()),
        "windows_test": int(te.sum()),
        "roc_auc": round(float(auc), 4),
        "pr_auc": round(float(ap), 4),
        "horizon_hours": HORIZON_H,
        "window_readings": WINDOW,
        "temperature_baseline_c": round(float(temp_thresh), 2),
        "detection_by_horizon": detect,
        "features": PROGNOSTIC_FEATURES,
    }


def main() -> None:
    if not DATASET1.exists():
        raise SystemExit(f"missing {DATASET1}")
    if not HISTORY.exists():
        raise SystemExit(f"missing {HISTORY} — run data/history_builder.py first")

    metrics = {
        "diagnostic": train_diagnostic(),
        "prognostic": train_prognostic(),
    }
    METRICS_OUT.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nwrote {METRICS_OUT.name}\n")


if __name__ == "__main__":
    main()

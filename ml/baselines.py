"""Scores the prognostic model against the threshold rules it has to beat.

    python ml/baselines.py

``ml/train.py`` reports one baseline — an **engine-temperature** threshold — because
that is the alarm fleets actually run today. It is the incumbent, not the strongest
threshold available in our own data, and saying so is cheaper than being caught.

This script measures the strongest one we found: a threshold on **vibration slope**,
which is feature 4 of the 26 the model already receives. Past 72 hours it beats the
model, and the honest framing is that neither is strictly better — the slope rule is an
earlier, much noisier smoke detector, and a fleet running this for real would run both.
Everything the README, `docs/architecture.md`, `DEMO_SCRIPT.md` and `HANDOFF.md` say
about that trade comes from here, via ``ml/baselines.json``.

Four questions, because "which is better" is not one question:

1. **Detection by horizon** — of the windows sitting N hours before a failure, what
   fraction does each rule fire on? This is where the slope rule wins long and loses near.
2. **Median lead time** — per failure, how early that rule first said something. Range.
3. **False alarms on machines that never fail** — the price of that range.
4. **Precision** — of everything a rule fires on, what fraction is inside a genuine
   degradation ramp rather than a healthy machine having a noisy afternoon.

Two rules of comparison, both of which exist to stop us flattering the model:

* The slope threshold is **rate-matched**: it is set so it fires on exactly as many
  held-out windows as the model does. A baseline allowed to alarm more often would win
  on detection for free, and comparing detection rates at different alarm rates is the
  oldest way to fake a win.
* The split is **by asset** and identical to training's — same seed, same 25% held out,
  same repair-gap rule via ``features.contiguous_windows``. Imported from ``train.py``
  rather than restated, so the two cannot drift.

Nothing here trains or writes a model. It loads the committed ``forecast_model.pkl`` and
measures it, so re-running after a retrain is how these figures stay true.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import PROGNOSTIC_FEATURES  # noqa: E402
from train import (  # noqa: E402
    HISTORY,
    HORIZON_H,
    _build_windows,
    _split_assets,
    _temperature_baseline,
)

FORECAST_MODEL = Path(__file__).resolve().parent / "forecast_model.pkl"
BASELINES_OUT = Path(__file__).resolve().parent / "baselines.json"

MODEL_THRESHOLD = 0.5
BANDS = [(120, 96), (96, 72), (72, 48), (48, 24), (24, 0)]

# The ramp in data/history_builder.py lasts DEGRADE_DAYS = 5.0. A window is "inside a
# real degradation ramp" exactly when the generator has begun degrading it, which it
# marks by writing a failing_component — so we read that column rather than re-deriving
# the 120-hour boundary and risking an off-by-one against the generator.


def _rate_matched_threshold(values: np.ndarray, n_alarms: int) -> float:
    """The threshold on ``values`` that fires exactly ``n_alarms`` times.

    The n-th largest value, so ``values >= threshold`` has the model's alarm budget and
    not a penny more. Ties can only push the count up, never down; with continuous
    slopes there are none.
    """
    if n_alarms <= 0:
        return float("inf")
    return float(np.sort(values)[::-1][n_alarms - 1])


def _episodes(assets: np.ndarray, htf: np.ndarray) -> list[np.ndarray]:
    """Split held-out windows into one run per upcoming failure.

    ``_build_windows`` emits windows already ordered by asset then time, so an episode
    ends wherever the asset changes, the countdown restarts (``hours_to_failure`` jumps
    back up after a repair), or the asset has no failure ahead of it at all. Each
    episode is one chance to warn, which is the unit a median lead time is a median of —
    not the window, of which a slow failure supplies more than a fast one.
    """
    eps: list[list[int]] = []
    cur: list[int] = []
    prev_asset: str | None = None
    prev_htf = np.nan
    for i in range(len(assets)):
        h = htf[i]
        if np.isnan(h):
            if cur:
                eps.append(cur)
                cur = []
            prev_asset, prev_htf = assets[i], h
            continue
        restarted = not np.isnan(prev_htf) and h > prev_htf
        if cur and (assets[i] != prev_asset or restarted):
            eps.append(cur)
            cur = []
        cur.append(i)
        prev_asset, prev_htf = assets[i], h
    if cur:
        eps.append(cur)
    return [np.array(e) for e in eps]


def _median_lead(eps: list[np.ndarray], htf: np.ndarray, fires: np.ndarray) -> float:
    """Median over failures of the earliest warning that rule gave.

    A failure the rule slept through scores 0 rather than being dropped. Dropping it
    would report the lead time of a rule that fires, which is not the same rule.
    """
    leads = []
    for e in eps:
        hit = fires[e]
        leads.append(float(htf[e][hit].max()) if hit.any() else 0.0)
    return float(np.median(leads)) if leads else 0.0


def main() -> None:
    if not HISTORY.exists():
        raise SystemExit(f"missing {HISTORY} — run data/history_builder.py first")
    if not FORECAST_MODEL.exists():
        raise SystemExit(f"missing {FORECAST_MODEL} — run ml/train.py first")

    print("\n" + "=" * 62)
    print("BASELINES  —  what does a plain threshold get us for free?")
    print("           (data/telemetry_history.csv)")
    print("=" * 62)

    df = pd.read_csv(HISTORY)
    print()
    X, _y, assets, htf, comp, _dropped = _build_windows(df)

    train_ids, test_ids = _split_assets(assets.tolist())
    te = np.isin(assets, list(test_ids))

    Xte = X[te]
    htf_te = htf[te]
    comp_te = comp[te]
    assets_te = assets[te]
    print(f"  {te.sum():,} held-out windows from {len(test_ids)} assets (split by asset)")

    # ── the three rules ─────────────────────────────────────────────────────
    bundle = joblib.load(FORECAST_MODEL)
    clf = bundle["models"][HORIZON_H]
    proba = clf.predict_proba(Xte)[:, 1]
    model_fires = proba >= MODEL_THRESHOLD

    slope_idx = PROGNOSTIC_FEATURES.index("vibration_mm_s_slope")
    slope_vals = Xte[:, slope_idx]
    slope_thresh = _rate_matched_threshold(slope_vals, int(model_fires.sum()))
    slope_fires = slope_vals >= slope_thresh

    temp_idx = PROGNOSTIC_FEATURES.index("engine_temp_c_last")
    temp_thresh = float(_temperature_baseline(df, assets)[0])
    temp_fires = Xte[:, temp_idx] >= temp_thresh

    rules = [
        ("model", model_fires),
        ("vibration_slope", slope_fires),
        ("engine_temp", temp_fires),
    ]
    print(f"  model      fires on {model_fires.sum():,} windows "
          f"({model_fires.mean():.1%}) at p >= {MODEL_THRESHOLD}")
    print(f"  vib slope  fires on {slope_fires.sum():,} windows "
          f"({slope_fires.mean():.1%}) at slope >= {slope_thresh:.4f}  [rate-matched]")
    print(f"  temp rule  fires on {temp_fires.sum():,} windows "
          f"({temp_fires.mean():.1%}) at {temp_thresh:.1f} C")

    # ── 1. detection by horizon ─────────────────────────────────────────────
    print("\n  Detection by horizon — of the windows N hours out, who fires?")
    print("  " + "-" * 58)
    print(f"  {'hours before failure':>22s}   {'model':>8s}   {'vib slope':>9s}   {'temp':>6s}")
    detect: dict[str, dict[str, float]] = {}
    for hi, lo in BANDS:
        band = (~np.isnan(htf_te)) & (htf_te <= hi) & (htf_te > lo)
        if band.sum() == 0:
            continue
        rates = {name: float(f[band].mean()) for name, f in rules}
        print(f"  {f'{lo}-{hi}h':>22s}   {rates['model']:>7.0%}   "
              f"{rates['vibration_slope']:>9.0%}   {rates['engine_temp']:>6.0%}")
        detect[f"{lo}-{hi}h"] = {
            "model_detection_rate": round(rates["model"], 4),
            "vibration_slope_detection_rate": round(rates["vibration_slope"], 4),
            "temperature_rule_detection_rate": round(rates["engine_temp"], 4),
            "n_windows": int(band.sum()),
        }

    # ── 2. median lead time ─────────────────────────────────────────────────
    eps = _episodes(assets_te, htf_te)
    lead = {name: _median_lead(eps, htf_te, f) for name, f in rules}
    print(f"\n  Median lead time over {len(eps)} held-out failures")
    print("  " + "-" * 58)
    for name, _f in rules:
        print(f"  {name:>22s}   {lead[name]:>6.0f} h")

    # ── 3. false alarms on machines that never fail ─────────────────────────
    # The price of range. A machine with no failure ahead of it at any point in the
    # history is one the rule has no excuse to alarm on, ever.
    never = sorted({a for a in test_ids if np.all(np.isnan(htf_te[assets_te == a]))})
    false_alarm = {
        name: int(sum(1 for a in never if f[assets_te == a].any())) for name, f in rules
    }
    print(f"\n  False alarms on the {len(never)} held-out machines that never fail")
    print("  " + "-" * 58)
    for name, _f in rules:
        print(f"  {name:>22s}   alarms on {false_alarm[name]:>2d} of {len(never)}")

    # ── 4. precision ────────────────────────────────────────────────────────
    in_ramp = comp_te != ""
    precision = {
        name: float(in_ramp[f].mean()) if f.any() else 0.0 for name, f in rules
    }
    print("\n  Precision — of everything it fires on, what is really degrading?")
    print("  " + "-" * 58)
    for name, f in rules:
        print(f"  {name:>22s}   {precision[name]:>6.1%}  ({int(f.sum()):,} firings)")

    print("\n  The slope rule sees further and cries wolf; the model is quiet and late.")
    print("  Neither dominates. A fleet would run the slope rule as a watch-list and")
    print("  the model to commit a truck.")

    out = {
        "windows_test": int(te.sum()),
        "test_assets": len(test_ids),
        "failures_test": len(eps),
        "never_failing_test_assets": len(never),
        "model_threshold": MODEL_THRESHOLD,
        "model_horizon_hours": HORIZON_H,
        "thresholds": {
            "vibration_slope": round(float(slope_thresh), 6),
            "vibration_slope_rate_matched_to": "model firing rate on the held-out split",
            "engine_temp_c": round(temp_thresh, 2),
        },
        "firings": {name: int(f.sum()) for name, f in rules},
        "firing_rate": {name: round(float(f.mean()), 4) for name, f in rules},
        "detection_by_horizon": detect,
        "median_lead_hours": {name: round(lead[name], 1) for name, _f in rules},
        "false_alarm_assets": false_alarm,
        "precision_in_ramp": {name: round(precision[name], 4) for name, _f in rules},
        "slope_feature": "vibration_mm_s_slope",
        "slope_feature_index": slope_idx,
    }
    BASELINES_OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {BASELINES_OUT.name}\n")


if __name__ == "__main__":
    main()

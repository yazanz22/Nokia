# ML — fault classification

Trains the 4-class fault classifier the agent's `predict_fault` tool calls.

- **Input:** `../data/dataset1.csv` (15k readings, 500 assets)
- **Features:** `telemetry_age_sec, signal_strength_dbm, neighbor_fail_count, engine_temp_c, reachable`
  (order defined in `backend/app/ml/client.py::FEATURES`)
- **Target:** `failure_reason` ∈ `{NORMAL, NETWORK_OUTAGE, DEVICE_FAILURE, SENSOR_FAILURE}`
- **Output:** `model.pkl` (loaded by the backend when present) + `metrics.json`

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python train.py
```

Until `model.pkl` exists, the backend falls back to a transparent rule-based classifier with the
identical interface, so the closed loop is demoable from day one.

## Planned (Day 5)

- `data_gen`/`augment.py` — optional noise + minority-class augmentation (the raw labels are cleanly
  separable, so a plain GradientBoosting model scores ≈1.0; augmentation makes the demo honest).
- `features.py` — feature builder shared with the backend.
- `train.py` — fit, stratified holdout, dump `model.pkl` + `metrics.json`.

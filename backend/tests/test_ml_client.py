from app.ml.client import fault_model
from app.models import TelemetrySample


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


def test_normal_reading():
    p = fault_model.predict("EQ-0001", _s())
    assert p.mode == "NORMAL"


def test_device_failure_signature():
    # unreachable, hot engine, strong signal, no neighbour failures
    p = fault_model.predict("EQ-0001", _s(reachable=False, engine_temp_c=120, signal_strength_dbm=-48))
    assert p.mode == "DEVICE_FAILURE"
    assert p.recommended_part == "HYD-PUMP-40L"
    assert p.confidence > 0.8


def test_network_outage_signature():
    p = fault_model.predict(
        "EQ-0001", _s(reachable=False, signal_strength_dbm=-124, neighbor_fail_count=8, engine_temp_c=85)
    )
    assert p.mode == "NETWORK_OUTAGE"


def test_sensor_failure_signature():
    p = fault_model.predict("EQ-0001", _s(telemetry_age_sec=45))
    assert p.mode == "SENSOR_FAILURE"

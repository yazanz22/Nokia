from app.seed import asset_pool, build_demo_fleet, build_technicians, load_rows


def test_dataset_loads():
    rows = load_rows()
    assert len(rows) == 15000
    labels = {r["failure_reason"] for r in rows}
    assert labels == {"NORMAL", "NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE"}


def test_demo_fleet_can_run_both_scenarios():
    fleet = build_demo_fleet(30)
    assert len(fleet) == 30
    pool = asset_pool()
    for asset in fleet:
        by_label = pool[asset.id]
        assert by_label["NETWORK_OUTAGE"], f"{asset.id} has no NETWORK_OUTAGE rows"
        assert by_label["DEVICE_FAILURE"], f"{asset.id} has no DEVICE_FAILURE rows"


def test_demo_fleet_is_deterministic():
    assert [a.id for a in build_demo_fleet(30)] == [a.id for a in build_demo_fleet(30)]


def test_technicians_cover_every_part():
    techs = build_technicians()
    carried = {p for t in techs for p in t.parts_on_hand}
    assert "HYD-PUMP-40L" in carried
    assert "TELEMETRY-SENSOR-KIT" in carried

"""Leaving the site is a warning, not an incident.

Every other outcome in this system starts with a machine going quiet and works
backwards to why. This one is the opposite and that is the entire point: the machine
is healthy, reporting, and about to drive out of coverage, and the value is reaching
the operator while all three are still true. If it ever produces an incident or a
dispatch, it has become a slower version of the roaming outcome and is worth nothing.
"""

import pytest

from app.nac.base import SITE_CENTER, SITE_RADIUS_KM, haversine_km
from app.nac.mock import MockNaCClient
from app.simulator import simulator
from app.store import store


def _walk_out(asset_id: str, ticks: int = 40) -> None:
    """Move an asset west until it is past the perimeter."""
    from app.simulator.engine import DRIFT_STEP_DEG

    asset = store.assets[asset_id]
    for _ in range(ticks):
        if haversine_km(asset.latitude, asset.longitude, *SITE_CENTER) > SITE_RADIUS_KM:
            return
        asset.longitude -= DRIFT_STEP_DEG


def test_every_demo_asset_starts_inside_the_perimeter():
    """Otherwise a machine is flagged for standing where we put it."""
    for a in store.assets.values():
        assert haversine_km(a.latitude, a.longitude, *SITE_CENTER) <= SITE_RADIUS_KM


def test_crossing_out_raises_an_alert_and_no_incident():
    asset_id = sorted(store.assets)[0]
    client = MockNaCClient()
    assert client.collect_geofence_events(list(store.assets.values())) == []

    _walk_out(asset_id)
    events = client.collect_geofence_events(list(store.assets.values()))
    assert [e.asset_id for e in events] == [asset_id]
    assert events[0].event_type == "area-left"

    store.raise_geofence_alert(events[0])

    assert store.assets[asset_id].offsite is True
    # The machine never failed, so nothing should have been opened or dispatched.
    assert store.assets[asset_id].state == "healthy"
    assert store.incidents == {}
    assert store.work_orders == {}
    assert store.incidents_prevented == 1
    assert len(store.geofence_alerts) == 1


def test_the_crossing_is_announced_once_not_every_tick():
    """Edge-triggered: a machine that is still outside is not news."""
    asset_id = sorted(store.assets)[0]
    client = MockNaCClient()
    client.collect_geofence_events(list(store.assets.values()))
    _walk_out(asset_id)

    first = client.collect_geofence_events(list(store.assets.values()))
    assert len(first) == 1
    for _ in range(5):
        assert client.collect_geofence_events(list(store.assets.values())) == []


def test_coming_back_clears_the_flag():
    asset_id = sorted(store.assets)[0]
    client = MockNaCClient()
    client.collect_geofence_events(list(store.assets.values()))
    _walk_out(asset_id)
    store.raise_geofence_alert(client.collect_geofence_events(list(store.assets.values()))[0])
    assert store.assets[asset_id].offsite is True

    store.assets[asset_id].latitude, store.assets[asset_id].longitude = SITE_CENTER
    back = client.collect_geofence_events(list(store.assets.values()))
    assert back and back[0].event_type == "area-entered"
    store.raise_geofence_alert(back[0])
    assert store.assets[asset_id].offsite is False


@pytest.mark.asyncio
async def test_drift_scenario_never_silences_the_machine():
    """The simulator must keep it transmitting, or the detector turns this into an
    ordinary incident and the whole distinction collapses."""
    asset_id = sorted(store.assets)[1]
    label = simulator.inject(asset_id, "offsite")
    assert label == "OFFSITE_DRIFT"
    assert not simulator.is_silent(asset_id)
    assert simulator.pending_label(asset_id) is None
    assert store.assets[asset_id].state == "healthy"

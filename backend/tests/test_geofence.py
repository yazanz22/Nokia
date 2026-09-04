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


def test_live_mode_still_delivers_geofence_events():
    """The fleet is simulated in both modes, so crossings must survive NAC_MODE=live.

    The wrapper used in live mode is a different class; when it simply lacked these
    methods the simulator's getattr check found nothing and geofencing vanished with
    no error anywhere — the same silent-in-live-mode failure that has bitten this
    codebase before.
    """
    from app.nac.factory import FallbackNaCClient

    client = FallbackNaCClient(live=MockNaCClient(), mock=MockNaCClient())
    assert callable(getattr(client, "collect_geofence_events", None))
    assert callable(getattr(client, "reset_geofence", None))

    asset_id = sorted(store.assets)[0]
    client.collect_geofence_events(list(store.assets.values()))
    _walk_out(asset_id)
    events = client.collect_geofence_events(list(store.assets.values()))
    assert [e.asset_id for e in events] == [asset_id]


def test_the_drift_stops_instead_of_running_off_the_map():
    """The projection fits its bounds to every asset.

    A machine that kept driving put itself 240 km out against a 119 km site, which
    rescales the map until the site is a smudge — on the frame the demo script leaves
    up while it closes.
    """
    from app.simulator.engine import DRIFT_STEP_DEG, DRIFT_STOP_KM

    asset_id = sorted(store.assets)[2]
    asset = store.assets[asset_id]
    simulator.inject(asset_id, "offsite")

    for _ in range(400):
        if asset_id not in simulator._drifting:
            break
        asset.longitude -= DRIFT_STEP_DEG
        if haversine_km(asset.latitude, asset.longitude, *SITE_CENTER) > SITE_RADIUS_KM + DRIFT_STOP_KM:
            simulator._drifting.discard(asset_id)

    out = haversine_km(asset.latitude, asset.longitude, *SITE_CENTER)
    assert out > SITE_RADIUS_KM, "must actually leave the site"
    assert out < SITE_RADIUS_KM + DRIFT_STOP_KM + 10, f"ran away to {out:.0f} km"

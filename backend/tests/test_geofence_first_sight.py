"""An asset that starts outside the perimeter has not just left it.

Geofencing is edge-triggered, so the client has to remember where each machine was
last time it looked. The failure this file guards is what it does *before* there is
anything to remember: assuming an unseen asset was inside turns "we have never
looked at this machine" into "this machine just drove off site" — a fabricated
warning, on a healthy asset, that also credits the Incidents-prevented KPI.

It is invisible at the demo fleet size because all 30 assets are placed inside. It
is not invisible at dataset scale: 23 of the 488 eligible assets sit beyond the
80 km perimeter, so a larger DEMO_FLEET_SIZE would open the dashboard on a handful
of crossings nobody made.
"""

from app.nac.base import SITE_CENTER, SITE_RADIUS_KM, haversine_km
from app.nac.mock import MockNaCClient
from app.store import store

# ~118 km west of the site centre, well clear of the 80 km boundary.
OUTSIDE = (SITE_CENTER[0], SITE_CENTER[1] - 1.2)


def _put(asset_id: str, position: tuple[float, float]):
    asset = store.assets[asset_id]
    asset.latitude, asset.longitude = position
    return asset


def _is_outside(asset) -> bool:
    return haversine_km(asset.latitude, asset.longitude, *SITE_CENTER) > SITE_RADIUS_KM


def test_an_asset_first_seen_outside_emits_no_crossing():
    asset_id = sorted(store.assets)[0]
    asset = _put(asset_id, OUTSIDE)
    assert _is_outside(asset), "fixture must actually start the asset off site"

    client = MockNaCClient()
    assert client.collect_geofence_events([asset]) == []
    # Still outside on the next pass, and still not news.
    assert client.collect_geofence_events([asset]) == []


def test_it_still_reports_the_crossings_that_really_happen():
    """Seeding must not cost us the events that matter — only the invented ones."""
    asset_id = sorted(store.assets)[0]
    asset = _put(asset_id, OUTSIDE)
    client = MockNaCClient()
    client.collect_geofence_events([asset])

    _put(asset_id, SITE_CENTER)
    entered = client.collect_geofence_events([asset])
    assert len(entered) == 1
    assert entered[0].event_type == "area-entered"
    assert entered[0].asset_id == asset_id

    _put(asset_id, OUTSIDE)
    left = client.collect_geofence_events([asset])
    assert len(left) == 1
    assert left[0].event_type == "area-left"
    assert left[0].asset_id == asset_id


def test_a_fleet_straddling_the_boundary_opens_silent():
    """The scaled-up case: some assets outside on boot, no alerts from any of them."""
    ids = sorted(store.assets)
    for asset_id in ids[:5]:
        _put(asset_id, OUTSIDE)
    subjects = list(store.assets.values())
    assert any(_is_outside(a) for a in subjects)

    client = MockNaCClient()
    assert client.collect_geofence_events(subjects) == []


def test_reset_does_not_leave_memory_that_fabricates_a_crossing():
    """reset_geofence() must forget, not remember an inside it never verified.

    Reset rebuilds the fleet, so the client's map of who is where is worthless the
    moment it is called. Anything it kept would be read as a crossing against the
    new positions.
    """
    asset_id = sorted(store.assets)[0]
    asset = _put(asset_id, OUTSIDE)
    client = MockNaCClient()
    client.collect_geofence_events([asset])

    client.reset_geofence()
    assert client.collect_geofence_events([asset]) == []

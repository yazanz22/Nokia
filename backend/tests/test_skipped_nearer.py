"""The work-order card must not call someone "nearer" at the distance it assigned.

`create_work_order` records a technician who was closer but passed over for not
carrying the part, so the assignment can defend itself instead of looking like a
routing bug on the map. That note was decided from full-precision haversine distances
while both numbers are stored — and rendered, by the card and by both agents' trace
text — rounded to a tenth of a kilometre. Eight metres of difference is enough to pass
the "genuinely nearer" test and vanish in the rounding, and the card then reads

    Ziad Khalifeh is nearer at 12.4 km ...

directly beneath an assigned technician printed at 12.4 km. One card contradicting
itself in its own two lines, on screen during the dispatch beat of the demo.

The distances here are built to land exactly on that tie: the skipped technician is
genuinely nearer, by less than the rounding can show.
"""

from __future__ import annotations

import pytest

from app.agent import tools
from app.agent.tools import create_work_order
from app.models import FaultPrediction, Technician, utcnow
from app.nac.base import DeviceLocation
from app.store import store

PART = "HYD-PUMP-40L"

# The asset. Crew are placed due north of it on the same meridian, where the haversine
# reduces to a clean 6371 * dlat radians — so a distance in km converts to a latitude
# offset exactly, and the tie below is constructed rather than hunted for.
ASSET_LAT = 27.5
ASSET_LON = 35.0
KM_PER_DEGREE_LAT = 6371.0 * 3.141592653589793 / 180.0


def _tech(tech_id: str, name: str, km: float, *, carries_part: bool) -> Technician:
    return Technician(
        id=tech_id,
        name=name,
        latitude=ASSET_LAT + km / KM_PER_DEGREE_LAT,
        longitude=ASSET_LON,
        available=True,
        parts_on_hand=[PART] if carries_part else ["TELEMETRY-SENSOR-KIT"],
    )


@pytest.fixture
def crew_stays_put(monkeypatch):
    """Keep the crafted positions.

    `create_work_order` asks CAMARA Location Retrieval where the crew are, and the mock
    answers with each technician's own position scattered inside a 15-60 m accuracy
    circle — which is larger than the 80 m gap this test is built on. The question here
    is what the comparison does with two distances, not where the distances came from.
    """

    async def _no_op(technicians):
        return "mock"

    monkeypatch.setattr(tools, "locate_crew", _no_op)


async def _order_for(assigned_km: float, skipped_km: float):
    """One dispatch, with exactly two technicians at the given distances."""
    store.technicians.clear()
    store.technicians["TECH-01"] = _tech("TECH-01", "Assigned Tech", assigned_km, carries_part=True)
    store.technicians["TECH-02"] = _tech("TECH-02", "Skipped Tech", skipped_km, carries_part=False)

    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    return await create_work_order(
        inc.id,
        asset_id,
        FaultPrediction(
            asset_id=asset_id,
            mode="DEVICE_FAILURE",
            confidence=0.99,
            recommended_part=PART,
            component="hydraulic_pump",
        ),
        DeviceLocation(
            asset_id=asset_id,
            latitude=ASSET_LAT,
            longitude=ASSET_LON,
            accuracy_m=25.0,
            as_of=utcnow(),
            source="mock",
        ),
    )


def test_the_tie_case_is_actually_a_tie():
    """Guard the fixture, not the code: if these stop rounding equal, the test is idle."""
    assigned = _tech("TECH-01", "Assigned Tech", 12.44, carries_part=True)
    skipped = _tech("TECH-02", "Skipped Tech", 12.36, carries_part=False)
    assigned_km = tools._haversine_km(assigned.latitude, assigned.longitude, ASSET_LAT, ASSET_LON)
    skipped_km = tools._haversine_km(skipped.latitude, skipped.longitude, ASSET_LAT, ASSET_LON)

    assert skipped_km < assigned_km, "the skipped technician has to be genuinely nearer"
    assert round(skipped_km, 1) == round(assigned_km, 1) == 12.4


@pytest.mark.asyncio
async def test_a_difference_too_small_to_print_is_not_announced(crew_stays_put):
    wo = await _order_for(assigned_km=12.44, skipped_km=12.36)

    assert wo.technician_name == "Assigned Tech"
    assert wo.distance_km == 12.4
    # The exact shape of the reported bug: the card claiming somebody is nearer at the
    # very number it just printed for the person it sent.
    assert wo.nearest_skipped_name == "", (
        f"the card would read '{wo.nearest_skipped_name} is nearer at "
        f"{wo.nearest_skipped_km:.1f} km' beside an assigned technician at "
        f"{wo.distance_km:.1f} km — the same distance"
    )
    assert wo.nearest_skipped_km == 0.0


@pytest.mark.asyncio
async def test_a_visibly_nearer_technician_is_still_named(crew_stays_put):
    """The fix suppresses the tie and nothing else — the note still has to work."""
    wo = await _order_for(assigned_km=30.0, skipped_km=8.0)

    assert wo.technician_name == "Assigned Tech"
    assert wo.nearest_skipped_name == "Skipped Tech"
    assert wo.nearest_skipped_km < wo.distance_km


@pytest.mark.asyncio
@pytest.mark.parametrize("assigned_km, skipped_km", [(12.44, 12.36), (30.0, 8.0), (8.0, 30.0)])
async def test_the_card_never_claims_nearer_at_a_distance_it_did_not_beat(
    crew_stays_put, assigned_km, skipped_km
):
    """The invariant behind both cases above, stated once against what is displayed.

    Whatever the geometry, a work order that names a skipped technician has to show a
    smaller number for them than for the person it sent — at the one decimal place both
    numbers are rendered with.
    """
    wo = await _order_for(assigned_km=assigned_km, skipped_km=skipped_km)

    if wo.nearest_skipped_name:
        assert wo.nearest_skipped_km < wo.distance_km
        assert f"{wo.nearest_skipped_km:.1f}" != f"{wo.distance_km:.1f}"

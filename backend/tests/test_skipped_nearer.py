"""The work-order card must not call someone "nearer" at the distance it assigned.

``create_work_order`` records a technician who was closer to the machine but would
have arrived later, so the assignment can defend itself instead of looking like a
routing bug on the map. Two things have to hold at once for that note to be honest:

* the skipped technician must be **visibly** nearer. The comparison used to be made on
  full-precision haversine distances while both numbers are stored — and rendered, by
  the card and by both agents' trace text — rounded to a tenth of a kilometre. Eight
  metres is enough to pass a "genuinely nearer" test and vanish in the rounding, and
  the card then reads

      Ziad Khalifeh is nearer at 12.4 km ...

  directly beneath an assigned technician printed at 12.4 km. One card contradicting
  itself in its own two lines, on screen during the dispatch beat of the demo.

* they must genuinely arrive **later**. Since the components moved into depots, being
  nearer the machine no longer implies being slower or faster to reach it — the
  journey is technician → depot → machine — so a note that says "nearer" without
  "later" is not an explanation of anything.

The geometry here is constructed rather than hunted for: the asset, the crew and the
depot all sit on one meridian, where the haversine reduces to ``6371 * dlat`` radians
and a distance in kilometres converts to a latitude offset exactly.
"""

from __future__ import annotations

import pytest

from app.agent import tools
from app.agent.tools import create_work_order
from app.models import FaultPrediction, Technician, Warehouse, utcnow
from app.nac.base import DeviceLocation
from app.store import store

PART = "HYD-PUMP-40L"

ASSET_LAT = 27.5
ASSET_LON = 35.0
KM_PER_DEGREE_LAT = 6371.0 * 3.141592653589793 / 180.0


def _lat(km: float) -> float:
    """A latitude ``km`` north of the asset."""
    return ASSET_LAT + km / KM_PER_DEGREE_LAT


def _tech(tech_id: str, name: str, km: float) -> Technician:
    """A technician ``km`` north of the machine. Everyone carries identical van stock."""
    return Technician(
        id=tech_id,
        name=name,
        latitude=_lat(km),
        longitude=ASSET_LON,
        available=True,
        parts_on_hand=["TELEMETRY-SENSOR-KIT"],
    )


@pytest.fixture
def crew_stays_put(monkeypatch):
    """Keep the crafted positions.

    ``create_work_order`` asks CAMARA Location Retrieval where the crew are, and the
    mock answers with each technician's own position scattered inside a 15-60 m
    accuracy circle — which is larger than the 80 m gap this test is built on. The
    question here is what the comparison does with two distances, not where the
    distances came from.
    """

    async def _no_op(technicians):
        return "mock"

    monkeypatch.setattr(tools, "locate_crew", _no_op)


async def _order_for(*, crew_km: dict[str, float], depot_km: float):
    """One dispatch, with the crew and the single stocking depot placed exactly."""
    store.technicians.clear()
    for i, (name, km) in enumerate(crew_km.items(), start=1):
        tid = f"TECH-{i:02d}"
        store.technicians[tid] = _tech(tid, name, km)

    # One depot, holding the one part, at a crafted distance. Replacing the seeded
    # pair rather than adding to them: with a second depot in play the routing has a
    # choice this test did not construct, and the arithmetic below stops describing it.
    store.warehouses.clear()
    store.warehouses["WH-T"] = Warehouse(
        id="WH-T",
        name="Test Depot",
        latitude=_lat(depot_km),
        longitude=ASSET_LON,
        stock={PART: 5},
    )

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
    near = tools._haversine_km(_lat(12.36), ASSET_LON, ASSET_LAT, ASSET_LON)
    far = tools._haversine_km(_lat(12.44), ASSET_LON, ASSET_LAT, ASSET_LON)

    assert near < far, "the skipped technician has to be genuinely nearer"
    assert round(near, 1) == round(far, 1) == 12.4


@pytest.mark.asyncio
async def test_a_difference_too_small_to_print_is_not_announced(crew_stays_put):
    """A depot beyond both technicians inverts the order by 80 metres, and the card
    must not announce a gap it cannot show."""
    wo = await _order_for(
        crew_km={"Assigned Tech": 12.44, "Skipped Tech": 12.36}, depot_km=100.0
    )

    # The depot is north of both, so the technician *further* from the machine is
    # marginally closer to the depot and wins the combined run.
    assert wo.technician_name == "Assigned Tech"
    # The exact shape of the reported bug: the card claiming somebody is nearer at the
    # very number it just printed for the person it sent.
    assert wo.nearest_skipped_name == "", (
        f"the card would read '{wo.nearest_skipped_name} is nearer at "
        f"{wo.nearest_skipped_km:.1f} km' beside an assigned technician whose own leg to "
        f"the machine rounds to the same number"
    )
    assert wo.nearest_skipped_km == 0.0
    assert wo.nearest_skipped_minutes_later == 0


@pytest.mark.asyncio
async def test_a_visibly_nearer_technician_is_still_named(crew_stays_put):
    """The suppression covers the tie and nothing else — the note still has to work.

    The depot sits beyond the far technician, so collecting the part costs the nearer
    one a long backtrack: closer to the machine, later to arrive.
    """
    wo = await _order_for(
        crew_km={"Assigned Tech": 30.0, "Skipped Tech": 8.0}, depot_km=40.0
    )

    assert wo.technician_name == "Assigned Tech"
    assert wo.nearest_skipped_name == "Skipped Tech"
    assert wo.nearest_skipped_km == 8.0
    # And the note earns its place: nearer, but genuinely later.
    assert wo.nearest_skipped_minutes_later > 0


@pytest.mark.asyncio
async def test_the_note_is_never_made_without_a_time_penalty(crew_stays_put):
    """Nearer *and sooner* is not a skip — it is the assignment.

    With the depot on the machine's side of the crew, the nearest technician is also
    the fastest, so there is nobody to explain away and the card stays quiet.
    """
    wo = await _order_for(
        crew_km={"Near Tech": 8.0, "Far Tech": 30.0}, depot_km=2.0
    )

    assert wo.technician_name == "Near Tech"
    assert wo.nearest_skipped_name == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "crew_km, depot_km",
    [
        ({"A": 12.44, "B": 12.36}, 100.0),
        ({"A": 30.0, "B": 8.0}, 40.0),
        ({"A": 8.0, "B": 30.0}, 40.0),
        ({"A": 8.0, "B": 30.0}, 2.0),
    ],
)
async def test_the_card_never_claims_nearer_at_a_distance_it_did_not_beat(
    crew_stays_put, crew_km, depot_km
):
    """The invariant behind every case above, stated once against what is displayed.

    Whatever the geometry, a work order that names a skipped technician has to show a
    smaller number for them than the assigned technician's own leg to the machine — at
    the one decimal place both are rendered with — and has to justify the choice with a
    non-zero time penalty.
    """
    wo = await _order_for(crew_km=crew_km, depot_km=depot_km)

    if wo.nearest_skipped_name:
        assigned_leg = round(wo.leg_to_asset_km, 1)
        assert wo.nearest_skipped_km < assigned_leg
        assert f"{wo.nearest_skipped_km:.1f}" != f"{assigned_leg:.1f}"
        assert wo.nearest_skipped_minutes_later > 0

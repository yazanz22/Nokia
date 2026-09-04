from app.seed import (
    COMPONENT_PARTS,
    PARTS_CATALOGUE,
    asset_pool,
    build_demo_fleet,
    build_technicians,
    load_rows,
)


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
    """Every part the agent can put on a work order has to be on somebody's truck.

    ``create_work_order`` filters the crew to whoever carries the required part and,
    finding nobody, *relaxes the constraint rather than failing to dispatch* — the
    right call at 3am with one part short, and a silent one. So a part that no
    technician carries does not break anything visibly: it quietly sends whoever is
    nearest, empty-handed, to a machine they cannot fix. Nothing else in the suite
    would notice.

    The old version named two of the five parts by hand — the hydraulic pump and the
    sensor kit — so the radiator core, the bearing set and the alternator could all
    have fallen off the roster with this test still green. Derived from the catalogues
    now, so a part added to either one is covered the day it is added.
    """
    required = {part for part, _ in COMPONENT_PARTS.values()}
    # The fallback kits, minus the two modes that dispatch nobody and so name no part.
    required |= {part for part, _ in PARTS_CATALOGUE.values() if part}
    # Deriving the expectation is only an improvement while the derivation finds
    # something: an emptied catalogue would make the subset check below vacuously true
    # and put the test straight back where it started.
    assert len(required) >= 5, f"catalogue shrank to {sorted(required)}"

    carried = {p for t in build_technicians() for p in t.parts_on_hand}
    assert not (required - carried), (
        f"no technician carries {sorted(required - carried)} — a work order naming one "
        "would be handed to whoever is nearest without it"
    )

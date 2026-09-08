from app.seed import (
    SERVICE_KIT_PART,
    VAN_STOCK,
    build_warehouses,
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


def test_every_part_is_obtainable_somewhere():
    """Every part the agent can put on a work order has to be reachable on this site.

    Either it rides in the van or a depot stocks it. A part in neither place is one no
    dispatch can ever satisfy: ``create_work_order`` finds no depot holding it, raises
    the job ``awaiting_part``, and nobody goes — correct behaviour for a genuine
    stock-out, and completely wrong as a permanent property of the catalogue. Nothing
    else in the suite would notice, because an unsatisfiable part looks exactly like an
    empty shelf.

    Derived from the catalogues rather than naming parts by hand, so a part added to
    either one is covered the day it is added.
    """
    required = {part for part, _ in COMPONENT_PARTS.values()}
    # The fallback kits, minus the two modes that dispatch nobody and so name no part.
    required |= {part for part, _ in PARTS_CATALOGUE.values() if part}
    required.add(SERVICE_KIT_PART)
    # Deriving the expectation is only an improvement while the derivation finds
    # something: an emptied catalogue would make the subset check below vacuously true
    # and put the test straight back where it started.
    assert len(required) >= 5, f"catalogue shrank to {sorted(required)}"

    obtainable = set(VAN_STOCK)
    for wh in build_warehouses():
        obtainable |= {p for p, units in wh.stock.items() if units > 0}
    assert not (required - obtainable), (
        f"nothing on this site can supply {sorted(required - obtainable)} — a work order "
        "naming one would be raised awaiting_part forever"
    )


def test_a_forward_depot_is_allowed_to_be_incomplete():
    """The routing is only interesting because the depots differ.

    If every depot stocked every part, the pickup would add a constant to every
    journey, never re-order the crew, and the two-leg routing would be theatre. This
    pins the asymmetry that makes it real — and would fail if somebody "fixed" the
    Trojena depot by giving it one of everything.
    """
    depots = build_warehouses()
    assert len(depots) >= 2
    stocked = [set(w.stock) for w in depots]
    assert stocked[0] != stocked[1], "the depots hold identical catalogues"
    assert any(s < set().union(*stocked) for s in stocked), "no depot is a forward store"

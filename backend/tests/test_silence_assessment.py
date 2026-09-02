"""Unit tests for the signal interpretation the dispatch guard depends on.

The LLM agent may skip the assessment tool and go straight from device status to
dispatch — it did exactly that in testing, and an earlier guard that relied on the
model having called `assess_coverage` silently failed to fire, sending a technician
to a machine that had merely crossed a border. The guard now recomputes this itself,
so these cases are the thing standing between a roaming asset and a wasted dispatch.
"""

from datetime import datetime, timezone

import pytest

from app.agent.tools import assess_silence
from app.nac.base import Reachability


def _reach(**kw) -> Reachability:
    base = dict(
        asset_id="EQ-0001",
        status="NOT_CONNECTED",
        signal_strength_dbm=-120.0,
        neighbor_fail_count=5,
        roaming=False,
        country="SA",
        as_of=datetime.now(timezone.utc),
        source="mock",
    )
    base.update(kw)
    return Reachability(**base)


def test_foreign_roaming_is_never_a_dispatch():
    v = assess_silence(_reach(status="CONNECTED_DATA", roaming=True, country="EG",
                              signal_strength_dbm=-71.0, neighbor_fail_count=0))
    assert v.category == "roaming_out"
    assert v.dispatch is False


def test_roaming_at_home_is_not_a_roaming_case():
    """Roaming within the home country is normal network behaviour, not a border crossing."""
    v = assess_silence(_reach(status="CONNECTED_DATA", roaming=True, country="SA"))
    assert v.category != "roaming_out"


def test_weak_signal_with_neighbour_failures_is_a_coverage_gap():
    v = assess_silence(_reach(signal_strength_dbm=-127.0, neighbor_fail_count=9))
    assert v.category == "coverage_gap"
    assert v.dispatch is False


def test_unreachable_on_a_strong_cell_is_the_machine():
    v = assess_silence(_reach(signal_strength_dbm=-52.0, neighbor_fail_count=0))
    assert v.category == "hardware"
    assert v.dispatch is True


def test_connected_still_reaches_the_fault_model():
    """A sensor fault presents as reachable-but-silent; it must not be short-circuited."""
    v = assess_silence(_reach(status="CONNECTED_DATA", signal_strength_dbm=-60.0,
                              neighbor_fail_count=0))
    assert v.dispatch is True

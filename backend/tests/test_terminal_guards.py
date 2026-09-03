"""Every terminal tool re-derives the verdict, not just the dispatching one.

The pitch says the model chooses *whether* to act but never *what* an action does,
because each terminal tool independently re-checks the network evidence. That was
only true of dispatch_technician. The two no-dispatch tools took the model's word
for it, so a genuine breakdown could be closed as a coverage gap or a roaming
ticket and nobody would ever be sent — a false negative that looks exactly like the
product working correctly.

These tests assert the property the deck claims, on the evidence rather than on the
model's intent.
"""

import pytest

from app.agent.tools import assess_silence
from app.models import utcnow
from app.nac.base import Reachability


def _reach(**kw) -> Reachability:
    base = dict(
        asset_id="EQ-0001", status="NOT_CONNECTED", signal_strength_dbm=-58.0,
        neighbor_fail_count=0, roaming=False, country="SA", source="mock", as_of=utcnow(),
    )
    base.update(kw)
    return Reachability(**base)


def test_strong_signal_is_not_a_coverage_gap():
    """The evidence a blind-spot claim needs, and this is not it."""
    v = assess_silence(_reach(signal_strength_dbm=-58.0, neighbor_fail_count=0))
    assert v.category == "hardware"
    assert v.dispatch is True


def test_weak_signal_with_neighbour_failures_is_a_coverage_gap():
    v = assess_silence(_reach(signal_strength_dbm=-127.0, neighbor_fail_count=12))
    assert v.category == "coverage_gap"
    assert v.dispatch is False


def test_home_network_roaming_is_not_a_roaming_event():
    """Roaming inside the home country is normal and must not block a dispatch."""
    v = assess_silence(_reach(roaming=True, country="SA"))
    assert v.category != "roaming_out"


def test_foreign_roaming_outranks_a_healthy_looking_radio():
    v = assess_silence(_reach(status="CONNECTED_DATA", roaming=True, country="JO"))
    assert v.category == "roaming_out"
    assert v.dispatch is False


@pytest.mark.parametrize(
    "kw, refused_category",
    [
        (dict(signal_strength_dbm=-58.0, neighbor_fail_count=0), "hardware"),
        (dict(status="CONNECTED_DATA"), "inconclusive"),
    ],
)
def test_blindspot_guard_refuses_when_evidence_is_absent(kw, refused_category):
    """The condition resolve_as_blindspot now checks before it will close anything."""
    assert assess_silence(_reach(**kw)).category == refused_category

"""Congestion Insights is the coverage evidence that survives a dark device.

CAMARA Device Status reports attachment and nothing about radio conditions, so
against a real operator signal strength and neighbour-cell counts arrive empty —
and the blind-spot verdict, which the whole demo opens with, becomes unreachable.
Every silence would look like a possible breakdown and get somebody sent.

These tests pin the fallback: congestion decides only when the radio metrics are
missing, and never overrides them when they are present.
"""

import pytest

from app.agent.tools import assess_silence
from app.models import utcnow
from app.nac.base import Reachability


def _reach(**kw) -> Reachability:
    base = dict(
        asset_id="EQ-0001", status="NOT_CONNECTED", signal_strength_dbm=None,
        neighbor_fail_count=None, roaming=False, country="SA",
        congestion_level=None, congestion_confidence=None,
        as_of=utcnow(), source="live",
    )
    base.update(kw)
    return Reachability(**base)


def test_no_evidence_at_all_stays_inconclusive():
    """Unchanged behaviour: absent both sources, lean toward checking the machine."""
    v = assess_silence(_reach())
    assert v.category == "inconclusive"
    assert v.dispatch is True


def test_high_congestion_makes_a_blind_spot_reachable_without_radio_metrics():
    v = assess_silence(_reach(congestion_level="High", congestion_confidence=72))
    assert v.category == "coverage_gap"
    assert v.dispatch is False
    assert "72%" in v.explanation


def test_low_congestion_exonerates_the_network_and_points_at_the_machine():
    v = assess_silence(_reach(congestion_level="Low", congestion_confidence=88))
    assert v.category == "hardware"
    assert v.dispatch is True


def test_low_confidence_decides_nothing_even_when_congestion_is_high():
    """The sandbox routinely returns High at 9-22% confidence.

    Acting on that would withhold a dispatch on the operator's own admission that it
    is unsure — leaving a broken machine in the desert on a guess.
    """
    v = assess_silence(_reach(congestion_level="High", congestion_confidence=22))
    assert v.category == "inconclusive"
    assert v.dispatch is True
    assert "22%" in v.explanation


def test_low_confidence_does_not_clear_the_network_either():
    """Symmetric: a weak 'Low' must not be grounds for rolling a truck."""
    v = assess_silence(_reach(congestion_level="Low", congestion_confidence=12))
    assert v.category == "inconclusive"


def test_confidence_at_the_floor_counts():
    v = assess_silence(_reach(congestion_level="High", congestion_confidence=50))
    assert v.category == "coverage_gap"


def test_medium_congestion_decides_nothing():
    """Not clean enough either way to spend or withhold a dispatch on."""
    v = assess_silence(_reach(congestion_level="Medium", congestion_confidence=50))
    assert v.category == "inconclusive"


@pytest.mark.parametrize("level", ["High", "Low"])
def test_radio_metrics_win_when_present(level):
    """Device-specific evidence outranks a statement about the neighbourhood.

    A strong last signal with no neighbour failures is about *this* device at the
    moment it went quiet; congestion is about the area. If they disagree, the
    specific one decides — otherwise a busy cell could excuse a broken machine.
    """
    v = assess_silence(_reach(
        signal_strength_dbm=-58.0, neighbor_fail_count=0,
        congestion_level=level, congestion_confidence=90,
    ))
    assert v.category == "hardware"


def test_foreign_roaming_still_outranks_congestion():
    v = assess_silence(_reach(
        status="CONNECTED_DATA", roaming=True, country="JO",
        congestion_level="High", congestion_confidence=90,
    ))
    assert v.category == "roaming_out"

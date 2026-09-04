"""Concrete actions the agent can take.

These are plain async functions with no tracing inside them. The rule agent calls
them directly; the Pydantic AI agent registers thin wrappers as tools. Keeping the
logic here means both agent modes take *exactly* the same actions.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import NamedTuple

from ..models import FaultPrediction, TelemetrySample, Technician, WorkOrder, utcnow
from ..nac import DeviceLocation, Reachability, get_network_client
from ..ml.client import fault_model
from ..store import store

# Serving-cell signal at/below this (dBm) is "weak"; combined with neighbour-cell
# failures it points to a genuine coverage gap rather than a dead machine.
WEAK_SIGNAL_DBM = -105.0

# The fleet's home network. NEOM sits at the head of the Gulf of Aqaba, within a few
# kilometres of Egyptian and Jordanian networks, so border roaming is a real event
# on this site rather than a hypothetical.
HOME_COUNTRY = "SA"

# CAMARA Congestion Insights grades the serving area, not the device — which makes it
# the one piece of coverage evidence that still arrives when the device is dark. It is
# the fallback, never the override: where the radio metrics exist they are specific to
# this device at the moment it went quiet, and a congested area is only ever a
# statement about the neighbourhood.
CONGESTION_BLAMES_NETWORK = {"High"}
CONGESTION_CLEARS_NETWORK = {"None", "Low"}

# Congestion Insights reports how sure the operator is, and below half sure it is not
# evidence — it is a guess with a number attached. Acting on it either way is a real
# mistake in both directions: withhold a dispatch on a low-confidence "High" and a
# broken machine sits in the desert; spend one on a low-confidence "Low" and a truck
# rolls for nothing. Under this floor the reading is reported and ignored, and the
# silence falls through to the fault model as it did before.
MIN_CONGESTION_CONFIDENCE = 50


async def check_device_status(asset_id: str) -> Reachability:
    return await get_network_client().get_reachability(asset_id)


async def get_device_location(asset_id: str) -> DeviceLocation:
    return await get_network_client().get_location(asset_id)


class SilenceVerdict(NamedTuple):
    """Why an asset went quiet, and whether that justifies sending anyone."""

    dispatch: bool          # should we go down the fault / dispatch path at all?
    category: str           # coverage_gap | roaming_out | hardware | inconclusive
    explanation: str


def assess_silence(reach: Reachability) -> SilenceVerdict:
    """Work out why a machine stopped reporting.

    Silence has more than one cause, and they need opposite responses. Reachability
    alone cannot separate them — that is the whole reason this calls more than one
    CAMARA API.
    """
    sig = reach.signal_strength_dbm
    nbr = reach.neighbor_fail_count or 0

    # Attached to a foreign network. The device is alive and on a network, it just
    # is not on OURS — so our telemetry APN never reaches the fleet backend. This is
    # invisible to reachability and to any on-board sensor; only the roaming API
    # reports it. It is a connectivity ticket, never a mechanic.
    if reach.roaming and reach.country and reach.country != HOME_COUNTRY:
        return SilenceVerdict(
            dispatch=False,
            category="roaming_out",
            explanation=(
                f"The device is reachable but roaming on a {reach.country} network. It has "
                "crossed onto a foreign operator near the site boundary, so its telemetry APN "
                "no longer reaches us. The machine is fine — this is a connectivity ticket, "
                "not a breakdown."
            ),
        )

    if reach.connected:
        # Attached to our own network yet not reporting. Connectivity is ruled out, so
        # this still needs the fault model — it is how a failed sensor on a healthy
        # machine presents, and how a transient dropout presents too.
        return SilenceVerdict(
            True, "inconclusive",
            "SIM is attached to our network — connectivity is not the problem, so the "
            "silence is something on the machine.",
        )

    if sig is not None and sig <= WEAK_SIGNAL_DBM and nbr >= 1:
        return SilenceVerdict(
            dispatch=False,
            category="coverage_gap",
            explanation=(
                f"Last serving-cell signal {sig:.0f} dBm with {nbr} neighbour-cell failures — "
                "the network dropped the device, not a fault on the machine."
            ),
        )

    if sig is not None and sig > WEAK_SIGNAL_DBM and nbr == 0:
        return SilenceVerdict(
            dispatch=True,
            category="hardware",
            explanation=(
                f"Device is unreachable but its last serving-cell signal was strong ({sig:.0f} dBm) "
                "with no neighbour-cell failures — the network is healthy here, so the silence is "
                "the equipment itself."
            ),
        )

    # No radio metrics. This is the normal case against a real operator: CAMARA Device
    # Status reports attachment and says nothing about signal, so without a second
    # source every coverage gap would present as a possible breakdown and get someone
    # sent. Congestion Insights is that second source.
    if sig is None and reach.congestion_level:
        conf = reach.congestion_confidence
        conf_text = f" at {conf}% confidence" if conf is not None else ""
        # A reading the operator is not confident in decides nothing. Say so out loud
        # rather than quietly discarding it — the number is on the dashboard, and an
        # operator who can see "High" needs to know why it did not count.
        if conf is not None and conf < MIN_CONGESTION_CONFIDENCE:
            return SilenceVerdict(
                True, "inconclusive",
                f"The operator reports {reach.congestion_level.lower()} congestion here but only "
                f"{conf}% confidence in that reading, which is too weak to decide either way. "
                "Treating the silence as a possible fault and handing it to the model.",
            )
        if reach.congestion_level in CONGESTION_BLAMES_NETWORK:
            return SilenceVerdict(
                dispatch=False,
                category="coverage_gap",
                explanation=(
                    f"No radio metrics from Device Status, but the operator reports "
                    f"{reach.congestion_level.lower()} congestion in this serving area"
                    f"{conf_text}. The device went quiet into a network that is already "
                    "struggling here — that is a coverage failure, not a breakdown."
                ),
            )
        if reach.congestion_level in CONGESTION_CLEARS_NETWORK:
            return SilenceVerdict(
                dispatch=True,
                category="hardware",
                explanation=(
                    f"The operator reports {reach.congestion_level.lower()} congestion in this "
                    f"serving area{conf_text}, so the network here is healthy. The device is "
                    "unreachable anyway — the silence is the equipment."
                ),
            )

    # Ambiguous — lean toward investigating hardware (a wasted check beats a missed breakdown).
    return SilenceVerdict(
        True, "inconclusive",
        "Network signal inconclusive; treating as a possible hardware fault pending ML review.",
    )


def predict_fault(asset_id: str, reach: Reachability | None = None) -> FaultPrediction:
    """Classify the fault from what the agent knows *now*.

    The last frame a machine transmitted is stamped reachable-and-fresh — it arrived,
    after all. But by the time we classify, the machine has gone quiet, and that
    silence is itself evidence. So we take the physical channels from the last frame
    and overlay the current network reality: whether CAMARA can still see the device,
    and how long it has actually been dark.

    Without this the model is asked about a state that never occurs in training
    (a red-hot engine on a device that is still answering) and extrapolates badly.
    """
    last = store.latest_telemetry.get(asset_id)
    if last is None:
        last = TelemetrySample(asset_id=asset_id)

    asset = store.assets.get(asset_id)
    silence_s = (utcnow() - asset.last_seen).total_seconds() if asset else last.telemetry_age_sec

    sample = last.model_copy(
        update={
            "reachable": reach.connected if reach is not None else last.reachable,
            "telemetry_age_sec": max(last.telemetry_age_sec, silence_s),
            "signal_strength_dbm": (
                reach.signal_strength_dbm
                if reach is not None and reach.signal_strength_dbm is not None
                else last.signal_strength_dbm
            ),
            "neighbor_fail_count": (
                reach.neighbor_fail_count
                if reach is not None and reach.neighbor_fail_count is not None
                else last.neighbor_fail_count
            ),
        }
    )
    return fault_model.predict(asset_id, sample)


def schedule_recheck(asset_id: str, minutes: int = 15) -> datetime:
    return utcnow() + timedelta(minutes=minutes)


def notify_operator(asset_id: str, message: str) -> str:
    # In production this fans out to the ops channel / PagerDuty. For the demo the
    # dashboard incident feed is the notification surface.
    return f"Operator notified: {message}"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def locate_crew(technicians: list[Technician]) -> str:
    """Ask the network where the available crew actually are.

    A technician's phone is a device on the same network as the machine, so the same
    CAMARA Location Retrieval call answers both halves of the dispatch question: where
    is the broken asset, and who is genuinely nearest to it. Rostered or last-known
    positions go stale the moment someone drives to a job — dispatching on them is how
    you send the second-nearest person.

    Best effort: a technician we cannot locate keeps their last known position rather
    than dropping out of consideration.
    """
    from ..config import get_settings

    settings = get_settings()
    client = get_network_client()

    # In live mode an unmapped subject falls back to the shared sandbox device, which
    # would put every technician on the same coordinates and make "nearest" meaningless.
    # Only locate crew with a device of their own; the rest keep their last position.
    mapped = settings.device_map()
    live = settings.nac_mode == "live"

    source = "seed"
    for tech in technicians:
        if live and tech.id not in mapped:
            continue
        try:
            loc = await client.get_location(tech.id)
        except Exception:  # noqa: BLE001 - an unlocatable crew member is not fatal
            continue
        tech.latitude = loc.latitude
        tech.longitude = loc.longitude
        tech.located_via = loc.source
        source = loc.source
    return source


async def create_work_order(
    incident_id: str,
    asset_id: str,
    fault: FaultPrediction,
    location: DeviceLocation,
) -> WorkOrder:
    part = fault.recommended_part

    # Establish where the whole available crew is *now*, once. Both questions below —
    # who is nearest with the part, and who was nearer without it — are answered from
    # the same set of positions. Locating twice would bill the Location Retrieval API
    # twice per dispatch and, worse, compare people measured at different moments.
    available = [t for t in store.technicians.values() if t.available]
    crew_source = await locate_crew(available)

    # Nearest available technician who carries the required part.
    candidates = [t for t in available if not part or part in t.parts_on_hand]
    if not candidates:  # relax the part constraint rather than fail to dispatch
        candidates = available

    # Someone closer who cannot fix it is not a better answer, but on a map it looks
    # like one. Record the skipped-but-nearer person so the reasoning is visible
    # instead of the dispatch appearing arbitrary.
    skipped_closer: Technician | None = None
    skipped_km = 0.0
    if part:
        for other in available:
            if part in other.parts_on_hand:
                continue
            km = _haversine_km(other.latitude, other.longitude,
                               location.latitude, location.longitude)
            if skipped_closer is None or km < skipped_km:
                skipped_closer, skipped_km = other, km

    tech = None
    distance = 0.0
    if candidates:
        tech, distance = min(
            (
                (t, _haversine_km(t.latitude, t.longitude, location.latitude, location.longitude))
                for t in candidates
            ),
            key=lambda pair: pair[1],
        )

    # Only worth mentioning if they were genuinely nearer than whoever we chose.
    # Otherwise the card would state something untrue.
    if skipped_closer is not None and skipped_km >= distance:
        skipped_closer = None

    wo = WorkOrder(
        id=store.next_work_order_id(),
        incident_id=incident_id,
        asset_id=asset_id,
        status="assigned" if tech else "created",
        fault_mode=fault.mode,
        component=fault.component,
        confidence=fault.confidence,
        part=part,
        asset_latitude=location.latitude,
        asset_longitude=location.longitude,
        technician_id=tech.id if tech else None,
        technician_name=tech.name if tech else "",
        technician_located_via=crew_source,
        distance_km=round(distance, 1),
        # ~45 km/h effective across a live construction site + 10 min mobilisation.
        eta_minutes=int(round(distance / 45.0 * 60)) + 10 if tech else 0,
        nearest_skipped_name=skipped_closer.name if skipped_closer else "",
        nearest_skipped_km=round(skipped_km, 1) if skipped_closer else 0.0,
    )
    store.add_work_order(wo)
    return wo

"""Concrete actions the agent can take.

These are plain async functions with no tracing inside them. The rule agent calls
them directly; the Pydantic AI agent registers thin wrappers as tools. Keeping the
logic here means both agent modes take *exactly* the same actions.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..models import FaultPrediction, TelemetrySample, WorkOrder, utcnow
from ..nac import DeviceLocation, Reachability, get_network_client
from ..ml.client import fault_model
from ..store import store

# Serving-cell signal at/below this (dBm) is "weak"; combined with neighbour-cell
# failures it points to a genuine coverage gap rather than a dead machine.
WEAK_SIGNAL_DBM = -105.0


async def check_device_status(asset_id: str) -> Reachability:
    return await get_network_client().get_reachability(asset_id)


async def get_device_location(asset_id: str) -> DeviceLocation:
    return await get_network_client().get_location(asset_id)


def assess_coverage_gap(reach: Reachability) -> tuple[bool, str]:
    """Disambiguate NOT_CONNECTED: coverage hole vs. hardware failure.

    Returns ``(is_coverage_gap, explanation)``.
    """
    if reach.connected:
        return False, "SIM is attached to the network — connectivity is not the problem."
    sig = reach.signal_strength_dbm
    nbr = reach.neighbor_fail_count or 0
    if sig is not None and sig <= WEAK_SIGNAL_DBM and nbr >= 1:
        return True, (
            f"Last serving-cell signal {sig:.0f} dBm with {nbr} neighbour-cell failures — "
            "the network dropped the device, not a fault on the machine."
        )
    if sig is not None and sig > WEAK_SIGNAL_DBM and nbr == 0:
        return False, (
            f"Device is unreachable but its last serving-cell signal was strong ({sig:.0f} dBm) "
            "with no neighbour-cell failures — the network is healthy here, so the silence is the "
            "equipment itself."
        )
    # Ambiguous — lean toward investigating hardware (a wasted check beats a missed breakdown).
    return False, "Network signal inconclusive; treating as a possible hardware fault pending ML review."


def predict_fault(asset_id: str) -> FaultPrediction:
    sample = store.latest_telemetry.get(asset_id)
    if sample is None:
        sample = TelemetrySample(asset_id=asset_id)
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


def create_work_order(
    incident_id: str,
    asset_id: str,
    fault: FaultPrediction,
    location: DeviceLocation,
) -> WorkOrder:
    part = fault.recommended_part
    # Nearest available technician who carries the required part.
    candidates = [
        t
        for t in store.technicians.values()
        if t.available and (not part or part in t.parts_on_hand)
    ]
    if not candidates:  # relax the part constraint rather than fail to dispatch
        candidates = [t for t in store.technicians.values() if t.available]

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

    wo = WorkOrder(
        id=store.next_work_order_id(),
        incident_id=incident_id,
        asset_id=asset_id,
        status="assigned" if tech else "created",
        fault_mode=fault.mode,
        confidence=fault.confidence,
        part=part,
        asset_latitude=location.latitude,
        asset_longitude=location.longitude,
        technician_id=tech.id if tech else None,
        technician_name=tech.name if tech else "",
        distance_km=round(distance, 1),
        # ~45 km/h effective across a live construction site + 10 min mobilisation.
        eta_minutes=int(round(distance / 45.0 * 60)) + 10 if tech else 0,
    )
    store.add_work_order(wo)
    return wo

"""Network-as-Code adapter contract.

Four CAMARA API families power the agent's network-verify step:

* **Device Status** (reachability / connectivity) — is the SIM attached to the network?
* **Device Roaming Status** — is it attached to somebody else's network?
* **Congestion Insights** — how is the serving *area* behaving?
* **Location Retrieval** — network-verified coordinates for a silent device.

(**Geofencing Subscriptions** is the fifth endpoint and the only one that pushes; it
watches the perimeter rather than answering a question about a silent machine, so it
runs alongside this contract rather than inside it.)

``reachable == False`` is ambiguous on its own — a dead engine and a coverage hole both
look "disconnected" — so the extra signals are what tell them apart.

``signal_strength_dbm`` and ``neighbor_fail_count`` are the sharpest of those, and they
are the ones a real operator does *not* give us: the dataset carries them as explicit
columns, and the live client leaves both ``None``. That gap is why Congestion Insights
is here. It grades the serving area rather than the device, so it still answers when the
device is dark — the fallback that keeps the coverage-gap verdict reachable outside the
mock. Where the radio metrics do exist they win, because they describe this device at
the moment it went quiet while congestion only describes the neighbourhood.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from ..models import utcnow

ReachStatus = Literal["CONNECTED_DATA", "CONNECTED_SMS", "NOT_CONNECTED", "UNKNOWN"]
# CAMARA Congestion Insights grades the serving area rather than the device.
CongestionLevel = Literal["None", "Low", "Medium", "High"]


class Reachability(BaseModel):
    asset_id: str
    status: ReachStatus
    signal_strength_dbm: float | None = None
    neighbor_fail_count: int | None = None
    # From CAMARA Device Roaming Status. A device roaming out of its home country is
    # a coverage/connectivity story, never a hardware one — the deck's
    # "Disconnected / Roaming Out" branch.
    roaming: bool | None = None
    country: str | None = None
    # From CAMARA Congestion Insights. Device Status answers "is it attached" and
    # nothing about radio conditions, so against a real operator the two fields above
    # arrive empty and a coverage gap is indistinguishable from a dead engine. This is
    # the network's own account of how degraded the serving area is, which is the
    # missing half of that judgement — and unlike signal strength it does not depend
    # on the silent device reporting anything.
    congestion_level: CongestionLevel | None = None
    congestion_confidence: int | None = None
    as_of: datetime
    source: Literal["live", "mock"]

    @property
    def connected(self) -> bool:
        """Attached to the network at all, by data or by SMS.

        Says nothing about whether telemetry can flow: an SMS-only attachment has no
        data session. For that question use ``data_connected``.
        """
        return self.status in ("CONNECTED_DATA", "CONNECTED_SMS")

    @property
    def data_connected(self) -> bool:
        """Attached with a data session, so telemetry could actually be sent.

        This is the question the silence diagnosis, the fault model and the automated
        re-check are all really asking. ``connected`` also counts SMS-only, and reading
        it here is how a device with no data bearer was taken for a healthy one.
        """
        return self.status == "CONNECTED_DATA"


class DeviceLocation(BaseModel):
    asset_id: str
    latitude: float
    longitude: float
    accuracy_m: float
    as_of: datetime
    source: Literal["live", "mock"]


class GeofenceEvent(BaseModel):
    """A device crossed a boundary the operator was watching for us.

    CAMARA Geofencing Subscriptions is push, not poll: you register an area and the
    network calls your sink when a device enters or leaves it. That is the whole
    value — you learn the machine is drifting out of coverage without asking, and
    crucially *while it is still reachable enough to tell you*.
    """

    asset_id: str
    event_type: Literal["area-left", "area-entered"]
    latitude: float
    longitude: float
    # How far past the boundary, so an operator can tell "just clipped it" from
    # "well on its way out".
    distance_km: float
    at: datetime
    source: Literal["live", "mock"]


@runtime_checkable
class NetworkClient(Protocol):
    async def get_reachability(self, asset_id: str) -> Reachability: ...
    async def get_location(self, asset_id: str) -> DeviceLocation: ...


# The operational site perimeter. Every demo asset starts inside it — the furthest
# is 73.8 km from this centre — so a machine outside has genuinely wandered rather
# than merely been placed awkwardly. NEOM sits at the head of the Gulf of Aqaba, so
# leaving to the west or north is leaving toward Egyptian or Jordanian coverage.
SITE_CENTER = (27.5581, 34.9196)
SITE_RADIUS_KM = 80.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _now() -> datetime:
    return utcnow()

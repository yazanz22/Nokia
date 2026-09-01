"""Network-as-Code adapter contract.

Two CAMARA-aligned signals power the agent's network-verify step:

* **Device Status** (reachability / connectivity) — is the SIM attached to the network?
* **Location Retrieval** — network-verified coordinates for a silent device.

We also surface ``signal_strength_dbm`` and ``neighbor_fail_count`` alongside
reachability. In the Nokia sandbox these come from the connectivity-insights
payload; in the dataset they are explicit columns. They matter because
``reachable == False`` is ambiguous on its own — a dead engine and a coverage
hole both look "disconnected" — and the agent needs the extra signal to tell
them apart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from ..models import utcnow

ReachStatus = Literal["CONNECTED_DATA", "CONNECTED_SMS", "NOT_CONNECTED", "UNKNOWN"]


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
    as_of: datetime
    source: Literal["live", "mock"]

    @property
    def connected(self) -> bool:
        return self.status in ("CONNECTED_DATA", "CONNECTED_SMS")


class DeviceLocation(BaseModel):
    asset_id: str
    latitude: float
    longitude: float
    accuracy_m: float
    as_of: datetime
    source: Literal["live", "mock"]


@runtime_checkable
class NetworkClient(Protocol):
    async def get_reachability(self, asset_id: str) -> Reachability: ...
    async def get_location(self, asset_id: str) -> DeviceLocation: ...


def _now() -> datetime:
    return utcnow()

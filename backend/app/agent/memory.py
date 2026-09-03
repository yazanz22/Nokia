"""Agent memory — what this fleet has taught us so far.

Without memory the agent is competent but amnesiac: an asset that has parked in the
same dead cell four times gets four identical full investigations, and the operator
never learns that the cell is the problem rather than the machine.

Memory is deliberately **structured, not semantic**. What the agent needs to recall
is "same asset, or same patch of ground — what happened last time?", which is an
exact lookup on an asset id and a map cell. A vector store would add an embedding
model and a similarity search to answer a question that has an exact answer. If
free-text recall over incident notes is ever wanted, Chroma (Resource & Tooling
Guide §4) drops in behind this same interface.

Memory intentionally **survives a fleet reset**. The fleet is demo state; what the
agent has learned about the terrain is not.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from ..models import utcnow

# ~0.02° ≈ 2 km. Big enough that an asset drifting around a work area lands in the
# same cell, small enough that a cell means a real place on the site.
CELL = 0.02

# Below this many prior coverage incidents a cell is just unlucky; at or above it,
# it is a property of the terrain worth telling the network team about.
KNOWN_DEAD_ZONE = 2

# Recent history is what informs a decision; a hundred episodes per key is far more
# than the counts above ever need, and bounds a long-running deployment.
MAX_PER_KEY = 100


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return (int(lat / CELL), int(lon / CELL))


@dataclass
class Episode:
    asset_id: str
    cell: tuple[int, int]
    category: str            # network_blindspot | roaming_blocked | hardware_confirmed | no_fault
    at: datetime = field(default_factory=utcnow)


@dataclass
class Recollection:
    """What the agent knows before it starts investigating."""

    asset_seen: int = 0
    cell_seen: int = 0
    cell_coverage_incidents: int = 0
    asset_hardware_failures: int = 0
    known_dead_zone: bool = False
    summary: str = ""

    @property
    def has_history(self) -> bool:
        return self.asset_seen > 0 or self.cell_seen > 0


class AgentMemory:
    def __init__(self) -> None:
        self._by_asset: dict[str, list[Episode]] = defaultdict(list)
        self._by_cell: dict[tuple[int, int], list[Episode]] = defaultdict(list)

    def record(self, asset_id: str, lat: float, lon: float, category: str) -> None:
        ep = Episode(asset_id=asset_id, cell=_cell(lat, lon), category=category)
        for bucket in (self._by_asset[asset_id], self._by_cell[ep.cell]):
            bucket.append(ep)
            if len(bucket) > MAX_PER_KEY:
                del bucket[:-MAX_PER_KEY]

        # Learning where the ground is bad is only useful if the operator sees it.
        if category in ("network_blindspot", "roaming_blocked"):
            from ..events import bus
            from ..models import WsEvent

            bus.publish(WsEvent(type="dead_zones", payload={"zones": self.dead_zones()}))

    def recall(self, asset_id: str, lat: float, lon: float) -> Recollection:
        cell = _cell(lat, lon)
        mine = self._by_asset.get(asset_id, [])
        here = self._by_cell.get(cell, [])
        coverage_here = [e for e in here if e.category in ("network_blindspot", "roaming_blocked")]
        hw = [e for e in mine if e.category == "hardware_confirmed"]

        r = Recollection(
            asset_seen=len(mine),
            cell_seen=len(here),
            cell_coverage_incidents=len(coverage_here),
            asset_hardware_failures=len(hw),
            known_dead_zone=len(coverage_here) >= KNOWN_DEAD_ZONE,
        )

        if not r.has_history:
            r.summary = "No prior incidents for this machine or this part of the site."
            return r

        parts: list[str] = []
        if r.known_dead_zone:
            parts.append(
                f"This patch of the site has produced {r.cell_coverage_incidents} connectivity "
                f"incidents already — it is a known dead zone, not a run of bad luck."
            )
        elif coverage_here:
            parts.append(
                f"{len(coverage_here)} previous connectivity incident(s) in this same area."
            )
        if r.asset_hardware_failures >= 2:
            parts.append(
                f"{asset_id} has had {r.asset_hardware_failures} confirmed hardware failures — "
                "worth reviewing for replacement rather than another repair."
            )
        elif mine:
            parts.append(f"{asset_id} has {len(mine)} prior incident(s) on record.")
        r.summary = " ".join(parts)
        return r

    def dead_zones(self) -> list[dict]:
        """Cells the agent has learned swallow signal, as map-drawable areas.

        This is the loop closing: the agent discovers dead ground by investigating,
        and the operator gets to see it. A coverage map nobody had to survey for.
        """
        out = []
        for cell, eps in self._by_cell.items():
            coverage = [e for e in eps if e.category in ("network_blindspot", "roaming_blocked")]
            if len(coverage) < KNOWN_DEAD_ZONE:
                continue
            lat_i, lon_i = cell
            out.append(
                {
                    # Cell centre, and the span so the map can draw the actual area.
                    "latitude": (lat_i + 0.5) * CELL,
                    "longitude": (lon_i + 0.5) * CELL,
                    "span": CELL,
                    "incidents": len(coverage),
                    "last_seen": max(e.at for e in coverage).isoformat(),
                }
            )
        return sorted(out, key=lambda z: -z["incidents"])

    @property
    def size(self) -> int:
        return sum(len(v) for v in self._by_asset.values())

    def clear(self) -> None:
        self._by_asset.clear()
        self._by_cell.clear()


memory = AgentMemory()

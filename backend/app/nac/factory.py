"""Pick the Network-as-Code client from config, with a resilient fallback.

In ``live`` mode every call is wrapped so that a sandbox/network error transparently
falls back to the dataset-backed mock — a venue Wi-Fi hiccup can't break the demo
(Resource & Tooling Guide §11: "agents that gracefully degrade demo much better").
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from ..config import get_settings
from .base import DeviceLocation, NetworkClient, Reachability
from .mock import MockNaCClient

log = logging.getLogger("nac")


# Which source answered each call, per caller rather than per client.
#
# `last_source` was one attribute on the shared singleton, overwritten by whichever
# call finished last, and every investigation on the site shares that one client: an
# agent falling back to the mock for a machine the sandbox has never heard of would
# flip it to "mock" between `/api/debug/nac`'s own two calls — or, the way that reads
# on stage, leave it saying "live" over a reachability the mock actually answered.
# That endpoint exists to answer "is this integration real?", and a wrong answer there
# is worse than no answer.
#
# A ContextVar is per asyncio task: each task gets its own copy of the context when it
# is created, so a request sees the sources of its own calls and nobody else's. Each
# write rebinds a fresh dict rather than mutating the one in place, so a task spawned
# mid-flow cannot write back into its parent's record either.
_call_sources: ContextVar[dict[str, str] | None] = ContextVar("nac_call_sources", default=None)


class FallbackNaCClient:
    """Try live, fall back to mock per-call."""

    def __init__(self, live: NetworkClient, mock: NetworkClient) -> None:
        self._live = live
        self._mock = mock

    @staticmethod
    def _note(call: str, source: str) -> None:
        sources = dict(_call_sources.get() or {})
        sources[call] = source
        _call_sources.set(sources)

    @property
    def last_call_sources(self) -> dict[str, str]:
        """Which source answered each CAMARA call this caller has made."""
        return dict(_call_sources.get() or {})

    @property
    def last_source(self) -> str:
        """One word for it, unless the calls disagree — in which case say so.

        The two calls behind `/api/debug/nac` can land differently: the sandbox knows
        the test device's reachability but the location retrieval times out, and
        collapsing that to "live" claims a live coordinate that came from the dataset.
        Naming both is the honest answer, and it is the answer that endpoint exists for.
        """
        sources = self.last_call_sources
        if not sources:
            return "unknown"
        distinct = set(sources.values())
        if len(distinct) == 1:
            return distinct.pop()
        return "mixed: " + ", ".join(f"{call}={src}" for call, src in sorted(sources.items()))

    async def get_reachability(self, asset_id: str) -> Reachability:
        try:
            r = await self._live.get_reachability(asset_id)
            self._note("reachability", "live")
            return r
        except Exception as exc:  # noqa: BLE001 - demo resilience is the point
            log.warning("live get_reachability failed for %s: %s — using mock", asset_id, exc)
            self._note("reachability", "mock")
            return await self._mock.get_reachability(asset_id)

    # Geofence events are about the *simulated fleet*, whose assets are not devices on
    # the sandbox — so there is nothing live to ask, in either mode, and these delegate
    # to the mock. Without them the wrapper simply lacks the attribute, and the tick's
    # getattr check quietly finds nothing: geofencing would disappear the moment
    # NAC_MODE=live, with no error anywhere. The genuine subscription against the
    # operator is a separate call, exercised by the live-check panel.
    def collect_geofence_events(self, subjects: list):
        collect = getattr(self._mock, "collect_geofence_events", None)
        return collect(subjects) if callable(collect) else []

    def reset_geofence(self) -> None:
        reset = getattr(self._mock, "reset_geofence", None)
        if callable(reset):
            reset()

    async def get_location(self, asset_id: str) -> DeviceLocation:
        try:
            loc = await self._live.get_location(asset_id)
            self._note("location", "live")
            return loc
        except Exception as exc:  # noqa: BLE001
            log.warning("live get_location failed for %s: %s — using mock", asset_id, exc)
            self._note("location", "mock")
            return await self._mock.get_location(asset_id)


_client: NetworkClient | None = None
_live: NetworkClient | None = None
_mock: MockNaCClient | None = None
_live_tried = False


def get_simulated_client() -> MockNaCClient:
    """The dataset-backed client, whatever NAC_MODE says.

    Assets and technicians are simulated in both modes — they are not devices on the
    sandbox and never will be — so anything asking where a *simulated* subject is has
    to ask this one. Reaching for the live client instead gets nothing useful and,
    worse, gets it silently.

    Deliberately a singleton: the geofence edge state lives on this object, and a
    second instance would believe every machine was still inside the perimeter.
    """
    global _mock
    if _mock is None:
        _mock = MockNaCClient()
    return _mock


def get_network_client() -> NetworkClient:
    """The client the *agent* uses while investigating fleet incidents."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    mock = get_simulated_client()
    if settings.nac_mode == "live":
        live = get_live_client()
        if live is not None:
            _client = FallbackNaCClient(live, mock)
            log.info("Network-as-Code: live sandbox (mock fallback armed)")
        else:
            log.warning("live NaC unavailable — using mock only")
            _client = mock
    else:
        _client = mock
        log.info("Network-as-Code: dataset-backed mock")
    return _client


def get_live_client() -> NetworkClient | None:
    """The real Nokia sandbox client, regardless of NAC_MODE.

    Kept separate from :func:`get_network_client` on purpose. The sandbox issues a
    handful of test SIMs that live in Hungary and always report reachable, so they
    cannot stand in for a 30-machine fleet spread across a NEOM site — a live
    location lookup would route every dispatch to Budapest.

    So the two are distinct and we say so out loud: the fleet simulation is served by
    the dataset-backed mock implementing the identical CAMARA contract, while this
    client answers the "is the integration actually real?" question with a genuine
    call anyone can watch.
    """
    global _live, _live_tried
    if _live is not None or _live_tried:
        return _live
    _live_tried = True
    settings = get_settings()
    if not settings.nac_api_key:
        log.info("no NAC_API_KEY — live CAMARA checks disabled")
        return None
    try:
        from .nokia import NokiaNaCClient

        _live = NokiaNaCClient()
        log.info("live CAMARA client ready (%s)", settings.nac_api_host)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not init live NaC client: %s", exc)
        _live = None
    return _live


def reset_network_client() -> None:
    global _client, _live, _mock, _live_tried
    _client = None
    _live = None
    _mock = None
    _live_tried = False

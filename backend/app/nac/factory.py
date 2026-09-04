"""Pick the Network-as-Code client from config, with a resilient fallback.

In ``live`` mode every call is wrapped so that a sandbox/network error transparently
falls back to the dataset-backed mock — a venue Wi-Fi hiccup can't break the demo
(Resource & Tooling Guide §11: "agents that gracefully degrade demo much better").
"""

from __future__ import annotations

import logging

from ..config import get_settings
from .base import DeviceLocation, NetworkClient, Reachability
from .mock import MockNaCClient

log = logging.getLogger("nac")


class FallbackNaCClient:
    """Try live, fall back to mock per-call."""

    def __init__(self, live: NetworkClient, mock: NetworkClient) -> None:
        self._live = live
        self._mock = mock
        self.last_source = "live"

    async def get_reachability(self, asset_id: str) -> Reachability:
        try:
            r = await self._live.get_reachability(asset_id)
            self.last_source = "live"
            return r
        except Exception as exc:  # noqa: BLE001 - demo resilience is the point
            log.warning("live get_reachability failed for %s: %s — using mock", asset_id, exc)
            self.last_source = "mock"
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
            self.last_source = "live"
            return loc
        except Exception as exc:  # noqa: BLE001
            log.warning("live get_location failed for %s: %s — using mock", asset_id, exc)
            self.last_source = "mock"
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

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


def get_network_client() -> NetworkClient:
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    mock = MockNaCClient()
    if settings.nac_mode == "live":
        try:
            from .nokia import NokiaNaCClient

            _client = FallbackNaCClient(NokiaNaCClient(), mock)
            log.info("Network-as-Code: live sandbox (mock fallback armed)")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not init live NaC client (%s) — using mock only", exc)
            _client = mock
    else:
        _client = mock
        log.info("Network-as-Code: dataset-backed mock")
    return _client


def reset_network_client() -> None:
    global _client
    _client = None

"""Live Nokia Network-as-Code adapter.

All SDK specifics are isolated here — the rest of the codebase only depends on the
:class:`NetworkClient` protocol in ``base.py``.

Written against the Fern-generated ``network_as_code`` **10.0.0** SDK, which is
what ``pip install network-as-code`` currently resolves to:

    from network_as_code import AsyncNetworkAsCodeApi
    api = AsyncNetworkAsCodeApi(api_key=KEY)                       # RapidAPI-hosted sandbox
    await api.device_status.check_connectivity(device={"phone_number": "+3197..."})
        -> .connectivity_status  ("CONNECTED_DATA" | "CONNECTED_SMS" | "NOT_CONNECTED")
    await api.location.retrieve(device={"phone_number": "+3197..."}, max_age=60)
        -> .area (circle: .center.latitude/.longitude, .radius) , .last_location_time

⚠️  SEAM: the two ``# --- SEAM`` blocks are the only places to touch if the FILO
sandbox entitles a different SDK/shape. Response parsing is deliberately defensive.
"""

from __future__ import annotations

from ..config import get_settings
from ..models import utcnow
from .base import DeviceLocation, Reachability, _now

_VALID = {"CONNECTED_DATA", "CONNECTED_SMS", "NOT_CONNECTED"}


def _first_attr(obj: object, *names: str, default=None):
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


class NokiaNaCClient:
    source = "live"

    def __init__(self) -> None:
        settings = get_settings()
        self._device_map = settings.device_map()
        from network_as_code import AsyncNetworkAsCodeApi  # lazy: mock mode needs no SDK

        kwargs: dict = {"api_key": settings.nac_api_key}
        if settings.nac_base_url:
            kwargs["base_url"] = settings.nac_base_url
        self._api = AsyncNetworkAsCodeApi(**kwargs)

    def _device(self, asset_id: str) -> dict:
        phone = self._device_map.get(asset_id)
        if not phone:
            raise KeyError(f"No sandbox device mapped for {asset_id} (set NAC_DEVICE_MAP)")
        return {"phone_number": phone}

    async def get_reachability(self, asset_id: str) -> Reachability:
        device = self._device(asset_id)
        # --- SEAM 1: device status --------------------------------------------
        resp = await self._api.device_status.check_connectivity(device=device)
        raw = _first_attr(resp, "connectivity_status", "status", default="UNKNOWN")
        status = str(getattr(raw, "value", raw)).upper()
        # --------------------------------------------------------------------
        return Reachability(
            asset_id=asset_id,
            status=status if status in _VALID else "UNKNOWN",
            signal_strength_dbm=None,  # not exposed by Device Status; comes from Congestion/Connectivity Insights
            neighbor_fail_count=None,
            as_of=_now(),
            source="live",
        )

    async def get_location(self, asset_id: str) -> DeviceLocation:
        device = self._device(asset_id)
        # --- SEAM 2: location retrieval -------------------------------------
        resp = await self._api.location.retrieve(device=device, max_age=60)
        area = _first_attr(resp, "area", default=resp)
        center = _first_attr(area, "center", "point", default=area)
        lat = float(_first_attr(center, "latitude", "lat", default=0.0))
        lon = float(_first_attr(center, "longitude", "lon", "lng", default=0.0))
        radius = _first_attr(area, "radius", "accuracy", default=None)
        last_time = _first_attr(resp, "last_location_time", default=None)
        # --------------------------------------------------------------------
        return DeviceLocation(
            asset_id=asset_id,
            latitude=lat,
            longitude=lon,
            accuracy_m=float(radius) if radius is not None else 50.0,
            as_of=last_time if hasattr(last_time, "year") else utcnow(),
            source="live",
        )

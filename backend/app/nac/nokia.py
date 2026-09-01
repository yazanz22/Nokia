"""Live Nokia Network as Code adapter — real CAMARA calls.

All SDK/transport specifics are isolated here; the rest of the codebase depends only
on the :class:`NetworkClient` protocol in ``base.py``.

Verified against the Nokia sandbox on 2026-09-01:

    POST /device-status/device-reachability-status/v1/retrieve  {"device":{...}}
        -> {"reachable": true, "connectivity": ["SMS"], "lastStatusTime": "..."}

    POST /device-status/v0/roaming        {"device":{"phoneNumber":"+999..."}}
        -> {"roaming": true, "countryCode": 36, "countryName": ["HU"], ...}

    POST /location-retrieval/v0/retrieve  {"device":{...}, "maxAge": 60}
        -> {"lastLocationTime": "...", "area": {"areaType":"CIRCLE",
            "center": {"latitude": .., "longitude": ..}, "radius": 1000}}

Reachability Status v1 is the primary call — it is the CAMARA API the solution is
built around, and its ``reachable`` flag maps directly onto the same field in our
telemetry. ``/device-status/v0/connectivity`` is kept as a fallback.

We call these directly with httpx rather than through the generated
``network-as-code`` SDK: the SDK defaults to a different base host, and the request
shape here is three small POSTs. Fewer moving parts to fail on stage.

Auth is RapidAPI-style: ``x-rapidapi-key`` plus ``x-rapidapi-host``.
"""

from __future__ import annotations

import logging

import httpx

from ..config import get_settings
from ..models import utcnow
from .base import DeviceLocation, Reachability, _now

log = logging.getLogger("nac.live")

_VALID = {"CONNECTED_DATA", "CONNECTED_SMS", "NOT_CONNECTED"}

REACHABILITY_PATH = "/device-status/device-reachability-status/v1/retrieve"
CONNECTIVITY_PATH = "/device-status/v0/connectivity"  # fallback
ROAMING_PATH = "/device-status/v0/roaming"
LOCATION_PATH = "/location-retrieval/v0/retrieve"


class NokiaNaCClient:
    """CAMARA Device Status + Location Retrieval against the Nokia sandbox."""

    source = "live"

    def __init__(self) -> None:
        settings = get_settings()
        self._device_map = settings.device_map()
        self._default_device = settings.nac_default_device.strip()
        self._client = httpx.AsyncClient(
            base_url=f"https://{settings.nac_api_host}",
            headers={
                "x-rapidapi-key": settings.nac_api_key,
                "x-rapidapi-host": settings.nac_rapidapi_host,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(settings.nac_timeout_seconds),
        )

    def _device(self, asset_id: str) -> dict:
        """Map a fleet asset to a sandbox device.

        The sandbox issues a small pool of test MSISDNs, far fewer than our fleet, so
        assets without an explicit mapping fall back to NAC_DEFAULT_DEVICE. That keeps
        the calls genuinely live for any asset instead of failing for most of them.
        """
        phone = self._device_map.get(asset_id) or self._default_device
        if not phone:
            raise KeyError(
                f"no sandbox device for {asset_id}: set NAC_DEVICE_MAP or NAC_DEFAULT_DEVICE"
            )
        return {"phoneNumber": phone}

    async def _post(self, path: str, payload: dict) -> dict:
        resp = await self._client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_reachability(self, asset_id: str) -> Reachability:
        device = self._device(asset_id)
        try:
            body = await self._post(REACHABILITY_PATH, {"device": device})
            # {"reachable": true, "connectivity": ["SMS"|"DATA"], ...}
            if body.get("reachable"):
                modes = [str(m).upper() for m in (body.get("connectivity") or [])]
                status = "CONNECTED_DATA" if "DATA" in modes else "CONNECTED_SMS"
            else:
                status = "NOT_CONNECTED"
        except Exception as exc:  # noqa: BLE001
            log.warning("reachability v1 failed (%s) — trying connectivity v0", exc)
            body = await self._post(CONNECTIVITY_PATH, {"device": device})
            status = str(body.get("connectivityStatus", "UNKNOWN")).upper()

        # Roaming is a second, independent CAMARA signal: a device roaming out of
        # country is a coverage story, not a hardware story. Best-effort — never let
        # it fail the primary reachability answer.
        roaming = None
        country = None
        try:
            r = await self._post(ROAMING_PATH, {"device": device})
            roaming = bool(r.get("roaming", False))
            names = r.get("countryName") or []
            country = names[0] if names else None
        except Exception as exc:  # noqa: BLE001
            log.debug("roaming lookup failed for %s: %s", asset_id, exc)

        return Reachability(
            asset_id=asset_id,
            status=status if status in _VALID else "UNKNOWN",
            # Device Status does not expose radio metrics; those come from the
            # telemetry side. Left as None so the agent knows they're unavailable
            # rather than reading a fabricated zero.
            signal_strength_dbm=None,
            neighbor_fail_count=None,
            roaming=roaming,
            country=country,
            as_of=_now(),
            source="live",
        )

    async def get_location(self, asset_id: str) -> DeviceLocation:
        device = self._device(asset_id)
        body = await self._post(LOCATION_PATH, {"device": device, "maxAge": 60})
        area = body.get("area") or {}
        center = area.get("center") or {}
        lat = float(center.get("latitude", 0.0))
        lon = float(center.get("longitude", 0.0))
        radius = area.get("radius")

        as_of = utcnow()
        raw_time = body.get("lastLocationTime")
        if raw_time:
            try:
                from datetime import datetime

                as_of = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            except ValueError:
                pass

        return DeviceLocation(
            asset_id=asset_id,
            latitude=lat,
            longitude=lon,
            accuracy_m=float(radius) if radius is not None else 1000.0,
            as_of=as_of,
            source="live",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

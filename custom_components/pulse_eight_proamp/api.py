"""Async HTTP client for the Pulse-Eight ProAmp8 amplifier.

The ProAmp8 exposes a small JSON-over-HTTP API on port 80. Endpoints and field
names are taken from Pulse-Eight's published API function reference and their
open-source Control4 / RTI drivers (github.com/Pulse-Eight/drivers).

Firmware revisions have used both camelCase (``volLeft``, ``pwrMode``,
``dolbyMode``) and snake_case (``volume_left``, ``power_mode``, ``dolby_mode``)
field names, so every reader here accepts either.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

NUM_ZONES = 8

# Power modes (amp/stdzone "pwrMode" / "power_mode")
POWER_MODE_OFF = 0
POWER_MODE_ON = 1
POWER_MODE_TRIGGER = 2
POWER_MODE_AUTO = 3


class ProAmpError(Exception):
    """Base error for the ProAmp client."""


class ProAmpConnectionError(ProAmpError):
    """The amplifier could not be reached or returned garbage."""


class ProAmpApiError(ProAmpError):
    """The amplifier answered but reported Result=false."""


def first_of(data: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    """Return the first key present (and not None) in ``data``."""
    if not data:
        return default
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    # Case-insensitive fallback - firmware is inconsistent about casing.
    lowered = {k.lower(): v for k, v in data.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return default


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@dataclass
class ZoneState:
    """State of one speaker output zone (0-based ``zone``)."""

    zone: int
    name: str | None = None
    volume: int | None = None
    muted: bool | None = None
    power_mode: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def number(self) -> int:
        """1-based zone number as printed on the amp."""
        return self.zone + 1


@dataclass
class ProAmpData:
    """Everything the coordinator polls in one cycle."""

    details: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    dolby: dict[str, Any] = field(default_factory=dict)
    zones: dict[int, ZoneState] = field(default_factory=dict)
    ports_raw: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)


def status_text(details: dict[str, Any]) -> str | None:
    """StatusMessage, or a description of the documented integer Status code."""
    msg = first_of(details, "StatusMessage")
    if msg:
        return str(msg)
    code = _to_int(first_of(details, "Status"))
    if code is None:
        return None
    return "Healthy" if code == 0 else f"Status code {code}"


def parse_zones(ports_response: dict[str, Any]) -> dict[int, ZoneState]:
    """Parse a /Port/List response into output zones."""
    zones: dict[int, ZoneState] = {}
    ports = first_of(ports_response, "Ports", "ports", default=[]) or []
    for port in ports:
        if str(first_of(port, "Mode", default="")).lower() != "output":
            continue
        bay = _to_int(first_of(port, "Bay"))
        if bay is None or not 0 <= bay < NUM_ZONES:
            continue
        mute = first_of(port, "mute", "muted")
        zones[bay] = ZoneState(
            zone=bay,
            name=first_of(port, "Name"),
            volume=_to_int(
                first_of(port, "volume", "volLeft", "volume_left", "dolbyvolume")
            ),
            muted=None if mute is None else _to_int(mute) not in (0, None),
            power_mode=_to_int(first_of(port, "pwrMode", "power_mode")),
            raw=port,
        )
    return zones


class ProAmpClient:
    """Minimal async client for one ProAmp8."""

    def __init__(
        self, host: str, session: aiohttp.ClientSession, timeout: float = 10
    ) -> None:
        host = host.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self._base = host
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # Serialise requests - the amp's embedded web server is small.
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Base URL of the amplifier."""
        return self._base

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base}/{path.lstrip('/')}"
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if payload is not None:
            kwargs["data"] = json.dumps(payload)
            kwargs["headers"] = {"Content-Type": "application/json"}
        async with self._lock:
            try:
                async with self._session.request(method, url, **kwargs) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise ProAmpConnectionError(
                            f"{method} {url} returned HTTP {resp.status}"
                        )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise ProAmpConnectionError(f"{method} {url} failed: {err}") from err
        try:
            data = json.loads(text)
        except ValueError as err:
            raise ProAmpConnectionError(f"{url} returned non-JSON: {text[:200]}") from err
        if not isinstance(data, dict):
            raise ProAmpConnectionError(f"{url} returned unexpected JSON: {data!r}")
        _LOGGER.debug("%s %s -> %s", method, url, data)
        return data

    async def _get(self, path: str, *, check: bool = True) -> dict[str, Any]:
        data = await self._request("GET", path)
        if check and data.get("Result") is False:
            raise ProAmpApiError(
                first_of(data, "ErrorMessage", "Message", default=f"{path} failed")
            )
        return data

    async def _post(
        self, path: str, payload: dict[str, Any], *, check: bool = True
    ) -> dict[str, Any]:
        data = await self._request("POST", path, payload)
        if check and data.get("Result") is False:
            raise ProAmpApiError(
                first_of(data, "ErrorMessage", "Message", default=f"{path} failed")
            )
        return data

    # ---- Read -------------------------------------------------------------

    async def get_details(self) -> dict[str, Any]:
        """Model, Serial, Version, StatusMessage, ... (/System/Details)."""
        return await self._get("System/Details")

    async def get_health(self) -> dict[str, Any]:
        """Temperature0..3 and Uptime in seconds (/System/Health)."""
        return await self._get("System/Health")

    async def get_ports(self) -> dict[str, Any]:
        """Raw /Port/List response (inputs and outputs)."""
        return await self._get("Port/List")

    async def get_features(self) -> dict[str, Any]:
        """StatusLED, BacklightLED, UpdInterval, ... (/System/Features)."""
        return await self._get("System/Features")

    async def get_dolby_settings(self) -> dict[str, Any]:
        """Global Dolby settings (/amp/dolbysettings)."""
        return await self._get("amp/dolbysettings")

    async def get_zone_volume(self, zone: int) -> dict[str, Any]:
        """Volume / mute for one zone (/Amp/Volume/{zone})."""
        return await self._get(f"Amp/Volume/{zone}")

    async def get_std_zones(self) -> dict[str, Any]:
        """Settings array for all zones (/Amp/StdZone with no body)."""
        return await self._get("Amp/StdZone")

    async def fetch_all(self, previous: ProAmpData | None = None) -> ProAmpData:
        """Poll everything needed for one coordinator refresh."""
        details = await self.get_details()
        ports = await self.get_ports()
        zones = parse_zones(ports)

        health: dict[str, Any] = {}
        try:
            health = await self.get_health()
        except ProAmpError as err:
            _LOGGER.debug("System/Health unavailable: %s", err)
            if previous:
                health = previous.health

        dolby: dict[str, Any] = {}
        try:
            dolby = await self.get_dolby_settings()
        except ProAmpError as err:
            _LOGGER.debug("amp/dolbysettings unavailable: %s", err)
            if previous:
                dolby = previous.dolby

        features: dict[str, Any] = {}
        try:
            features = await self.get_features()
        except ProAmpError as err:
            _LOGGER.debug("System/Features unavailable: %s", err)
            if previous:
                features = previous.features

        # Make sure all 8 zones exist even if Port/List omitted some.
        for zone in range(NUM_ZONES):
            zones.setdefault(zone, ZoneState(zone=zone))

        # Older firmware: Port/List may not carry volume/mute - ask per zone.
        for state in zones.values():
            if state.volume is None or state.muted is None:
                try:
                    vol = await self.get_zone_volume(state.zone)
                except ProAmpError as err:
                    _LOGGER.debug("Volume for zone %s unavailable: %s", state.zone, err)
                    continue
                if state.volume is None:
                    state.volume = _to_int(
                        first_of(vol, "volLeft", "dolbyvolume", "volume", "volume_left")
                    )
                if state.muted is None:
                    mute = first_of(vol, "muted", "mute")
                    if mute is not None:
                        state.muted = _to_int(mute) not in (0, None)

        # Older firmware: power mode only available from Amp/StdZone.
        if any(z.power_mode is None for z in zones.values()):
            await self._fill_power_modes(zones)

        return ProAmpData(
            details=details, health=health, dolby=dolby, zones=zones, ports_raw=ports,
            features=features,
        )

    async def _fill_power_modes(self, zones: dict[int, ZoneState]) -> None:
        try:
            data = await self.get_std_zones()
        except ProAmpError as err:
            _LOGGER.debug("Amp/StdZone unavailable: %s", err)
            return
        entries = first_of(data, "zones", "Zones", "settings", "Settings", default=None)
        if entries is None:
            entries = [v for v in data.values() if isinstance(v, dict)]
        if isinstance(entries, dict):
            entries = list(entries.values())
        for index, entry in enumerate(entries or []):
            if not isinstance(entry, dict):
                continue
            zone = _to_int(first_of(entry, "zone", default=index))
            if zone in zones and zones[zone].power_mode is None:
                zones[zone].power_mode = _to_int(
                    first_of(entry, "pwrMode", "power_mode")
                )

    # ---- Write ------------------------------------------------------------

    async def set_volume(self, zone: int, level: int) -> dict[str, Any]:
        """Set both channels of a zone to ``level`` (0-100)."""
        level = max(0, min(100, int(level)))
        return await self._get(f"Amp/Volume/{zone}/{level}")

    async def volume_up(self, zone: int) -> dict[str, Any]:
        """Step zone volume up by one."""
        return await self._get(f"Amp/Volume/{zone}/up")

    async def volume_down(self, zone: int) -> dict[str, Any]:
        """Step zone volume down by one."""
        return await self._get(f"Amp/Volume/{zone}/down")

    async def set_mute(self, zone: int, muted: bool) -> dict[str, Any]:
        """Mute/unmute both channels (channel 3 = both)."""
        return await self._get(f"Amp/Mute/{zone}/3/{1 if muted else 0}")

    async def set_power_mode(self, zone: int, mode: int) -> dict[str, Any]:
        """Set zone power mode: 0 off, 1 on, 2 12V trigger, 3 auto-sense."""
        if mode not in (POWER_MODE_OFF, POWER_MODE_ON, POWER_MODE_TRIGGER, POWER_MODE_AUTO):
            raise ValueError(f"Invalid power mode {mode}")
        # Current firmware (per Pulse-Eight's Control4 driver) uses snake_case;
        # the older published reference uses pwrMode. Try new, fall back to old.
        try:
            return await self._post("Amp/StdZone", {"zone": zone, "power_mode": mode})
        except ProAmpApiError:
            return await self._post("Amp/StdZone", {"zone": zone, "pwrMode": mode})

    async def set_status_led(self, on: bool) -> dict[str, Any]:
        """Front-panel status LEDs (POST /System/StatusLED/{on|off})."""
        # capitalised, as used against real MatrixOS hardware
        return await self._request("POST", f"System/StatusLED/{'On' if on else 'Off'}", {})

    async def restart(self) -> None:
        """Reboot the amplifier."""
        try:
            await self._request("GET", "System/Restart")
        except ProAmpConnectionError:
            # The amp may drop the connection as it reboots.
            pass

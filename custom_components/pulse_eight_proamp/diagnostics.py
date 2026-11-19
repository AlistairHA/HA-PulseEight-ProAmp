"""Diagnostics for the Pulse-Eight ProAmp8 (Settings > Devices > Download diagnostics)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import MAC_KEYS
from .coordinator import ProAmpConfigEntry

TO_REDACT = {"Serial", "serial", "InstallerId", *MAC_KEYS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ProAmpConfigEntry
) -> dict[str, Any]:
    """Return raw API payloads so unmapped firmware fields can be identified."""
    data = entry.runtime_data.data
    return {
        "entry": {"title": entry.title, "options": dict(entry.options)},
        "details": async_redact_data(data.details, TO_REDACT),
        "health": data.health,
        "dolby": data.dolby,
        "port_list": data.ports_raw,
        "zones": {z: asdict(s) for z, s in data.zones.items()},
    }

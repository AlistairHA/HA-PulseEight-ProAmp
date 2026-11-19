"""Data update coordinator for the Pulse-Eight ProAmp8."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ProAmpClient, ProAmpData, ProAmpError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type ProAmpConfigEntry = ConfigEntry[ProAmpCoordinator]


class ProAmpCoordinator(DataUpdateCoordinator[ProAmpData]):
    """Polls one ProAmp8."""

    config_entry: ProAmpConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ProAmpConfigEntry, client: ProAmpClient
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client

    async def _async_update_data(self) -> ProAmpData:
        try:
            return await self.client.fetch_all(self.data)
        except ProAmpError as err:
            raise UpdateFailed(f"Error communicating with ProAmp8: {err}") from err

    async def async_command(self, coro) -> None:
        """Run a write command, translating errors for the UI, then refresh."""
        try:
            await coro
        except ProAmpError as err:
            raise HomeAssistantError(f"ProAmp8 command failed: {err}") from err
        # Push optimistic state now, then confirm from the amp shortly after.
        self.async_update_listeners()
        await self.async_request_refresh()

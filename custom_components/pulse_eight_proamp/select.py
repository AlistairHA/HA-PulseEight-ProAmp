"""Per-zone power mode for the Pulse-Eight ProAmp8."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import NUM_ZONES
from .const import POWER_MODES, POWER_MODES_REVERSE
from .coordinator import ProAmpConfigEntry, ProAmpCoordinator
from .entity import ProAmpZoneEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProAmpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up power mode selects."""
    coordinator = entry.runtime_data
    async_add_entities(ProAmpPowerMode(coordinator, z) for z in range(NUM_ZONES))


class ProAmpPowerMode(ProAmpZoneEntity, SelectEntity):
    """Zone power mode: Off / On / 12V trigger / Auto-sense."""

    _attr_translation_key = "zone_power_mode"
    _attr_options = list(POWER_MODES)

    def __init__(self, coordinator: ProAmpCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "power_mode")

    @property
    def current_option(self) -> str | None:
        state = self.zone_state
        if state is None or state.power_mode is None:
            return None
        return POWER_MODES_REVERSE.get(state.power_mode)

    async def async_select_option(self, option: str) -> None:
        mode = POWER_MODES[option]
        if self.zone_state:
            self.zone_state.power_mode = mode
        await self.coordinator.async_command(
            self.coordinator.client.set_power_mode(self._zone, mode)
        )

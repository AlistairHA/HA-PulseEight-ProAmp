"""Per-zone volume control for the Pulse-Eight ProAmp8."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import NUM_ZONES
from .coordinator import ProAmpConfigEntry, ProAmpCoordinator
from .entity import ProAmpZoneEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProAmpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up volume numbers."""
    coordinator = entry.runtime_data
    async_add_entities(ProAmpVolume(coordinator, z) for z in range(NUM_ZONES))


class ProAmpVolume(ProAmpZoneEntity, NumberEntity):
    """Zone volume, 0-100 (the amp maps this onto the zone's dB range)."""

    _attr_translation_key = "zone_volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: ProAmpCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "volume")

    @property
    def native_value(self) -> float | None:
        state = self.zone_state
        return state.volume if state else None

    async def async_set_native_value(self, value: float) -> None:
        level = int(round(value))
        if self.zone_state:
            self.zone_state.volume = level
        await self.coordinator.async_command(
            self.coordinator.client.set_volume(self._zone, level)
        )

"""Per-zone mute for the Pulse-Eight ProAmp8."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.const import EntityCategory

from .api import NUM_ZONES, first_of
from .coordinator import ProAmpConfigEntry, ProAmpCoordinator
from .entity import ProAmpEntity, ProAmpZoneEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProAmpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up mute switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ProAmpMute(coordinator, z) for z in range(NUM_ZONES)]
    if first_of(coordinator.data.features, "StatusLED") is not None:
        entities.append(ProAmpStatusLed(coordinator))
    async_add_entities(entities)


class ProAmpMute(ProAmpZoneEntity, SwitchEntity):
    """Zone mute (both channels)."""

    _attr_translation_key = "zone_mute"

    def __init__(self, coordinator: ProAmpCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "mute")

    @property
    def is_on(self) -> bool | None:
        state = self.zone_state
        return state.muted if state else None

    async def _set(self, muted: bool) -> None:
        if self.zone_state:
            self.zone_state.muted = muted
        await self.coordinator.async_command(
            self.coordinator.client.set_mute(self._zone, muted)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class ProAmpStatusLed(ProAmpEntity, SwitchEntity):
    """Front-panel status LEDs (System/StatusLED)."""

    _attr_translation_key = "status_led"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ProAmpCoordinator) -> None:
        super().__init__(coordinator, "status_led")

    @property
    def is_on(self) -> bool | None:
        value = first_of(self.coordinator.data.features, "StatusLED")
        return None if value is None else str(value).lower() not in ("off", "0", "false")

    async def _set(self, on: bool) -> None:
        self.coordinator.data.features["StatusLED"] = "on" if on else "off"
        await self.coordinator.async_command(self.coordinator.client.set_status_led(on))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

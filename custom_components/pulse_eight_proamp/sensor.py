"""Sensors for the Pulse-Eight ProAmp8: system info, hardware and health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import ProAmpData, first_of, status_text
from .const import DOLBY_MODES, HOSTNAME_KEYS, HW_REV_KEYS, MAC_KEYS
from .coordinator import ProAmpConfigEntry, ProAmpCoordinator
from .entity import ProAmpEntity

PARALLEL_UPDATES = 0


def _dolby_mode(data: ProAmpData) -> str | None:
    raw = first_of(data.dolby, "dolbyMode", "dolby_mode")
    try:
        return DOLBY_MODES.get(int(raw))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class ProAmpSensorDescription(SensorEntityDescription):
    """Describes a ProAmp sensor."""

    value_fn: Callable[[ProAmpData], Any]
    exists_fn: Callable[[ProAmpData], bool] = lambda _: True


def _detail(*keys: str) -> Callable[[ProAmpData], Any]:
    return lambda d: first_of(d.details, *keys)


def _has_detail(*keys: str) -> Callable[[ProAmpData], bool]:
    return lambda d: first_of(d.details, *keys) is not None


SENSORS: tuple[ProAmpSensorDescription, ...] = (
    # --- System information ---
    ProAmpSensorDescription(
        key="status",
        translation_key="status",
        value_fn=lambda d: status_text(d.details),
    ),
    ProAmpSensorDescription(
        key="dolby_mode",
        translation_key="dolby_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(DOLBY_MODES.values()),
        value_fn=_dolby_mode,
        exists_fn=lambda d: bool(d.dolby),
    ),
    # --- Hardware details ---
    ProAmpSensorDescription(
        key="model",
        translation_key="model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_detail("Model"),
    ),
    ProAmpSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_detail("Version", "FirmwareVersion"),
    ),
    ProAmpSensorDescription(
        key="serial",
        translation_key="serial",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_detail("Serial"),
    ),
    ProAmpSensorDescription(
        key="mac",
        translation_key="mac",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_detail(*MAC_KEYS),
        exists_fn=_has_detail(*MAC_KEYS),
    ),
    ProAmpSensorDescription(
        key="hardware_revision",
        translation_key="hardware_revision",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_detail(*HW_REV_KEYS),
        exists_fn=_has_detail(*HW_REV_KEYS),
    ),
    ProAmpSensorDescription(
        key="hostname",
        translation_key="hostname",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_detail(*HOSTNAME_KEYS),
        exists_fn=_has_detail(*HOSTNAME_KEYS),
    ),
)


def _temperature_sensor(index: int) -> ProAmpSensorDescription:
    key = f"Temperature{index}"
    return ProAmpSensorDescription(
        key=f"temperature_{index}",
        translation_key="temperature",
        translation_placeholders={"index": str(index + 1)},
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: first_of(d.health, key, f"temperature{index}"),
        exists_fn=lambda d: first_of(d.health, key, f"temperature{index}") is not None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProAmpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    data = coordinator.data
    descriptions = list(SENSORS) + [_temperature_sensor(i) for i in range(4)]
    entities: list[SensorEntity] = [
        ProAmpSensor(coordinator, desc) for desc in descriptions if desc.exists_fn(data)
    ]
    if first_of(data.health, "Uptime") is not None:
        entities.append(ProAmpLastBootSensor(coordinator))
    async_add_entities(entities)


class ProAmpSensor(ProAmpEntity, SensorEntity):
    """Generic ProAmp sensor."""

    entity_description: ProAmpSensorDescription

    def __init__(
        self, coordinator: ProAmpCoordinator, description: ProAmpSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.translation_placeholders:
            self._attr_translation_placeholders = dict(
                description.translation_placeholders
            )

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.coordinator.data)
        if isinstance(value, (dict, list)):
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        # Expose the full /System/Details payload on the status sensor so any
        # hardware fields not mapped to dedicated sensors are still visible.
        if self.entity_description.key != "status":
            return None
        return {
            k: v
            for k, v in self.coordinator.data.details.items()
            if k not in ("Result",) and not isinstance(v, (dict, list))
        }


class ProAmpLastBootSensor(ProAmpEntity, SensorEntity):
    """Boot time derived from the uptime counter (avoids per-poll state churn)."""

    _attr_translation_key = "last_boot"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ProAmpCoordinator) -> None:
        super().__init__(coordinator, "last_boot")
        self._boot: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        uptime = first_of(self.coordinator.data.health, "Uptime")
        try:
            seconds = float(uptime)
        except (TypeError, ValueError):
            return self._boot
        boot = (dt_util.utcnow() - timedelta(seconds=seconds)).replace(microsecond=0)
        if self._boot is None or abs((boot - self._boot).total_seconds()) > 60:
            self._boot = boot
        return self._boot

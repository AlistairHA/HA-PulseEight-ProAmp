"""Base entities for the Pulse-Eight ProAmp8 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ZoneState, first_of
from .const import DEFAULT_MODEL, DOMAIN, HW_REV_KEYS, MAC_KEYS, MANUFACTURER
from .coordinator import ProAmpCoordinator


class ProAmpEntity(CoordinatorEntity[ProAmpCoordinator]):
    """An entity belonging to the amplifier device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ProAmpCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._serial = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{self._serial}_{key}"
        self._attr_device_info = build_device_info(coordinator)


def build_device_info(coordinator: ProAmpCoordinator) -> DeviceInfo:
    """Device registry info for the amplifier."""
    details = coordinator.data.details if coordinator.data else {}
    model_id = first_of(details, "Model")
    info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.unique_id)},
        manufacturer=MANUFACTURER,
        model=DEFAULT_MODEL,
        model_id=str(model_id) if model_id else None,
        name=coordinator.config_entry.title.split(" (")[0],
        serial_number=coordinator.config_entry.unique_id,
        sw_version=first_of(details, "Version", "FirmwareVersion"),
        hw_version=(str(hw) if (hw := first_of(details, *HW_REV_KEYS)) is not None else None),
        configuration_url=coordinator.client.base_url,
    )
    mac = first_of(details, *MAC_KEYS)
    if mac:
        info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(str(mac)))}
    return info


class ProAmpZoneEntity(ProAmpEntity):
    """An entity for one output zone (shown on the amplifier device)."""

    def __init__(self, coordinator: ProAmpCoordinator, zone: int, key: str) -> None:
        super().__init__(coordinator, f"zone{zone + 1}_{key}")
        self._zone = zone
        self._attr_translation_placeholders = {"zone_name": self._zone_label()}

    def _zone_label(self) -> str:
        number = self._zone + 1
        state = self.zone_state
        name = (state.name or "").strip() if state else ""
        generic = {"", f"output {number}", f"zone {number}", f"output{number}", str(number)}
        if name.lower() in generic:
            return f"Zone {number}"
        return f"Zone {number} {name}"

    @property
    def zone_state(self) -> ZoneState | None:
        """Current polled state of this zone."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.zones.get(self._zone)

    @property
    def available(self) -> bool:
        return super().available and self.zone_state is not None

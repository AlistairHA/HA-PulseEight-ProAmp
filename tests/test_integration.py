"""End-to-end tests of the ProAmp8 integration against the fake amp."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState, SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.pulse_eight_proamp.const import DOMAIN

from .conftest import HOST, SERIAL, FakeProAmp


def eid(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}")
    assert entity_id, f"no {platform} entity for {key}"
    return entity_id


async def setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_device_and_sensors(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SERIAL)})
    assert device is not None
    assert device.manufacturer == "Pulse-Eight"
    assert device.model == "ProAmp8"
    assert device.sw_version == "1.4.12"
    assert device.hw_version == "B2"
    assert device.serial_number == SERIAL
    assert (dr.CONNECTION_NETWORK_MAC, "00:1e:c0:aa:bb:cc") in device.connections
    assert device.configuration_url == f"http://{HOST}"

    assert hass.states.get(eid(hass, "sensor", "status")).state == "System Healthy"
    assert hass.states.get(eid(hass, "sensor", "firmware")).state == "1.4.12"
    assert hass.states.get(eid(hass, "sensor", "model")).state == "PROAMP8"
    assert hass.states.get(eid(hass, "sensor", "serial")).state == SERIAL
    assert hass.states.get(eid(hass, "sensor", "mac")).state == "00:1E:C0:AA:BB:CC"
    assert hass.states.get(eid(hass, "sensor", "hardware_revision")).state == "B2"
    assert hass.states.get(eid(hass, "sensor", "dolby_mode")).state == "off"
    t1 = hass.states.get(eid(hass, "sensor", "temperature_1"))
    assert float(t1.state) == 41.0
    assert t1.attributes["unit_of_measurement"] == "°C"
    assert t1.name == "ProAmp8 Temperature 2"
    boot = dt_util.parse_datetime(hass.states.get(eid(hass, "sensor", "last_boot")).state)
    assert abs((dt_util.utcnow() - boot).total_seconds() - 93784) < 5

    # Every entity is attached to the one amp device.
    entities = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert {e.device_id for e in entities} == {device.id}
    # 8 sensors-ish + 4 temps + boot + 8*(volume, power, mute) + restart
    assert len([e for e in entities if e.domain == "number"]) == 8
    assert len([e for e in entities if e.domain == "select"]) == 8
    assert len([e for e in entities if e.domain == "switch"]) == 9  # 8 mutes + status LEDs

    led = eid(hass, "switch", "status_led")
    assert hass.states.get(led).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": led}, blocking=True)
    await hass.async_block_till_done()
    assert mock_amp.status_led == "Off" and hass.states.get(led).state == "off"


async def test_zone_names(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    names = [hass.states.get(eid(hass, "number", f"zone{z}_volume")).name for z in range(1, 9)]
    assert names[0] == "ProAmp8 Zone 1 Kitchen volume"
    assert names[2] == "ProAmp8 Zone 3 volume"  # generic "Output 3" collapsed
    assert names[3] == "ProAmp8 Zone 4 volume"  # blank name
    power = hass.states.get(eid(hass, "select", "zone1_power_mode"))
    assert power.name == "ProAmp8 Zone 1 Kitchen power mode"


async def test_volume_control(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    entity = eid(hass, "number", "zone2_volume")
    assert hass.states.get(entity).state == "25"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity, "value": 63}, blocking=True
    )
    await hass.async_block_till_done()
    assert mock_amp.zones[1]["volume"] == 63
    assert hass.states.get(entity).state == "63"
    assert hass.states.get(entity).attributes["max"] == 100


async def test_power_mode_control(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    entity = eid(hass, "select", "zone7_power_mode")
    state = hass.states.get(entity)
    assert state.state == "auto_sense"
    assert state.attributes["options"] == ["off", "on", "trigger_12v", "auto_sense"]

    for option, value in (("trigger_12v", 2), ("off", 0), ("on", 1)):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity, "option": option}, blocking=True
        )
        await hass.async_block_till_done()
        assert mock_amp.zones[6]["pwr"] == value
        assert hass.states.get(entity).state == option
    assert mock_amp.power_mode_posts[-1] == {"zone": 6, "power_mode": 1}


async def test_mute_control(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    entity = eid(hass, "switch", "zone5_mute")
    assert hass.states.get(entity).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity}, blocking=True)
    await hass.async_block_till_done()
    assert mock_amp.zones[4]["mute"] == 1
    assert hass.states.get(entity).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity}, blocking=True)
    await hass.async_block_till_done()
    assert mock_amp.zones[4]["mute"] == 0


async def test_restart_button(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    entity = eid(hass, "button", "restart")
    await hass.services.async_call("button", "press", {"entity_id": entity}, blocking=True)
    assert mock_amp.restarted


async def test_external_change_is_polled(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    mock_amp.zones[0]["volume"] = 77  # changed from the amp's web UI / keypad
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "number", "zone1_volume")).state == "77"


async def test_goes_unavailable_and_recovers(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    await setup(hass, config_entry)
    entity = eid(hass, "number", "zone1_volume")
    mock_amp.online = False
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == STATE_UNAVAILABLE
    mock_amp.online = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=22))
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "20"


async def test_setup_retry_when_offline(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    mock_amp.online = False
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("fake_amp", [FakeProAmp(legacy=True)])
async def test_legacy_firmware_fallbacks(hass: HomeAssistant, mock_amp: FakeProAmp, config_entry) -> None:
    """Port/List without volume/power -> per-zone Volume + StdZone; pwrMode POST fallback."""
    await setup(hass, config_entry)
    # documented System/Details layout: integer BoardRev and Status, no StatusMessage
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SERIAL)})
    assert device.hw_version == "2"
    assert hass.states.get(eid(hass, "sensor", "status")).state == "Healthy"
    assert er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{SERIAL}_status_led") is None
    assert hass.states.get(eid(hass, "number", "zone3_volume")).state == "30"
    entity = eid(hass, "select", "zone1_power_mode")
    assert hass.states.get(entity).state == "on"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity, "option": "trigger_12v"}, blocking=True
    )
    await hass.async_block_till_done()
    assert mock_amp.zones[0]["pwr"] == 2
    assert mock_amp.power_mode_posts[-2:] == [
        {"zone": 0, "power_mode": 2},
        {"zone": 0, "pwrMode": 2},
    ]
    assert hass.states.get(entity).state == "trigger_12v"


async def test_unload(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


# ---- Config flow -----------------------------------------------------------

async def test_config_flow_success(hass: HomeAssistant, mock_amp) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"ProAmp8 ({HOST})"
    assert result["data"] == {"host": HOST}
    assert result["result"].unique_id == SERIAL


async def test_config_flow_cannot_connect(hass: HomeAssistant, mock_amp: FakeProAmp) -> None:
    mock_amp.online = False
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_duplicate(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"scan_interval": 30}
    assert config_entry.runtime_data.update_interval == timedelta(seconds=30)


async def test_diagnostics_redacts(hass: HomeAssistant, mock_amp, config_entry) -> None:
    from custom_components.pulse_eight_proamp.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["details"]["Serial"] == "**REDACTED**"
    assert diag["details"]["MAC"] == "**REDACTED**"
    assert len(diag["port_list"]["Ports"]) == 16


async def test_reconfigure_changes_host(hass: HomeAssistant, mock_amp, config_entry) -> None:
    await setup(hass, config_entry)
    hass.config_entries.async_update_entry(config_entry, data={"host": "10.0.0.9"})
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {"host": HOST}

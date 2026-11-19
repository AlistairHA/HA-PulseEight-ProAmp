"""Fixtures: a stateful fake ProAmp8 that speaks the HTTP/JSON API."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from yarl import URL

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.pulse_eight_proamp.const import DOMAIN

HOST = "192.168.1.50"
SERIAL = "P8PA8-000123"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components in every test."""
    yield


class FakeProAmp:
    """In-memory ProAmp8. ``legacy`` mimics older firmware field layout."""

    def __init__(self, legacy: bool = False) -> None:
        self.legacy = legacy
        self.online = True
        self.restarted = False
        self.power_mode_posts: list[dict[str, Any]] = []
        self.status_led = "on"
        names = ["Kitchen", "Lounge", "Output 3", "", "Dining", "Patio", "Bathroom", "Office"]
        self.zones = [
            {"volume": 20 + i * 5, "mute": 0, "pwr": 1 if i < 6 else 3, "name": names[i]}
            for i in range(8)
        ]

    # -- responses ---------------------------------------------------------
    def details(self) -> dict[str, Any]:
        if self.legacy:  # layout exactly as in the official API docs
            return {"Result": True, "Model": "PROAMP8", "Version": "1.2.0", "Serial": SERIAL,
                    "MAC": "00:1E:C0:AA:BB:CC", "VID": "P8", "BoardRev": 2, "Status": 0}
        return {
            "Result": True,
            "Model": "PROAMP8",
            "Serial": SERIAL,
            "Version": "1.4.12",
            "StatusMessage": "System Healthy",
            "MAC": "00:1E:C0:AA:BB:CC",
            "HardwareRevision": "B2",
        }

    def health(self) -> dict[str, Any]:
        return {
            "Result": True,
            "Temperature0": 38.5,
            "Temperature1": 41.0,
            "Temperature2": 39.25,
            "Temperature3": 36.0,
            "Uptime": 93784,
        }

    def ports(self) -> dict[str, Any]:
        ports = []
        for i in range(8):
            ports.append({"Bay": i, "Mode": "Input", "Name": f"Input {i + 1}"})
            out = {"Bay": i, "Mode": "Output", "Name": self.zones[i]["name"], "ReceiveFrom": i}
            if not self.legacy:
                out |= {
                    "volume": self.zones[i]["volume"],
                    "mute": self.zones[i]["mute"],
                    "pwrMode": self.zones[i]["pwr"],
                }
            ports.append(out)
        return {"Result": True, "Ports": ports}

    # -- router ------------------------------------------------------------
    def handle(self, method: str, url: URL, data: Any) -> tuple[int, dict[str, Any]]:
        if not self.online:
            raise TimeoutError
        path = url.path.lower().strip("/")
        parts = path.split("/")
        if path == "system/details":
            return 200, self.details()
        if path == "system/health":
            return 200, self.health()
        if path == "system/features" and not self.legacy:
            return 200, {"Result": True, "CEC": None, "UpdInterval": 3600000,
                         "BacklightLED": "high", "StatusLED": self.status_led}
        if parts[:2] == ["system", "statusled"] and method.upper() == "POST":
            self.status_led = url.path.strip("/").split("/")[2]
            return 200, {"Result": True, "Message": "Changed"}
        if path == "system/restart":
            self.restarted = True
            return 200, {"Result": True}
        if path == "port/list":
            return 200, self.ports()
        if path == "amp/dolbysettings":
            return 200, {"Result": True, "dolby_mode": 0, "pcmUpMixF": 0}
        if parts[:2] == ["amp", "volume"]:
            zone = int(parts[2])
            z = self.zones[zone]
            if len(parts) >= 4:
                arg = parts[3]
                if arg == "up":
                    z["volume"] = min(100, z["volume"] + 1)
                elif arg == "down":
                    z["volume"] = max(0, z["volume"] - 1)
                else:
                    z["volume"] = int(arg)
            return 200, {"Result": True, "volLeft": z["volume"], "volRight": z["volume"], "muted": z["mute"]}
        if parts[:2] == ["amp", "mute"]:
            zone, channel, state = int(parts[2]), int(parts[3]), int(parts[4])
            assert channel == 3
            self.zones[zone]["mute"] = state
            return 200, {"Result": True, "mute": state}
        if path == "amp/stdzone":
            if method.upper() == "POST":
                body = json.loads(data)
                self.power_mode_posts.append(body)
                key = "pwrMode" if self.legacy else "power_mode"
                if key not in body:
                    return 200, {"Result": False, "ErrorMessage": "Invalid field"}
                self.zones[body["zone"]]["pwr"] = body[key]
                return 200, {"Result": True, "Message": "Zone updated"}
            return 200, {
                "Result": True,
                "zones": [{"zone": i, "pwrMode": z["pwr"]} for i, z in enumerate(self.zones)],
            }
        return 404, {"Result": False, "ErrorMessage": "Not found"}


@pytest.fixture
def fake_amp() -> FakeProAmp:
    return FakeProAmp()


@pytest.fixture
def mock_amp(aioclient_mock: AiohttpClientMocker, fake_amp: FakeProAmp) -> FakeProAmp:
    """Route all HTTP traffic for HOST to the fake amp."""

    async def _side_effect(method, url, data):
        try:
            status, body = fake_amp.handle(method, url, data)
        except TimeoutError as err:
            return AiohttpClientMockResponse(method, url, exc=err)
        return AiohttpClientMockResponse(method, url, status=status, text=json.dumps(body))

    pattern = re.compile(rf"^http://{re.escape(HOST)}/")
    aioclient_mock.get(pattern, side_effect=_side_effect)
    aioclient_mock.post(pattern, side_effect=_side_effect)
    return fake_amp


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"ProAmp8 ({HOST})",
        data={"host": HOST},
        unique_id=SERIAL,
    )

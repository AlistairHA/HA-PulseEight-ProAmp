"""Constants for the Pulse-Eight ProAmp8 integration."""

from __future__ import annotations

from .api import POWER_MODE_AUTO, POWER_MODE_OFF, POWER_MODE_ON, POWER_MODE_TRIGGER

DOMAIN = "pulse_eight_proamp"
MANUFACTURER = "Pulse-Eight"
DEFAULT_MODEL = "ProAmp8"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 300

# select option key <-> API value
POWER_MODES: dict[str, int] = {
    "off": POWER_MODE_OFF,
    "on": POWER_MODE_ON,
    "trigger_12v": POWER_MODE_TRIGGER,
    "auto_sense": POWER_MODE_AUTO,
}
POWER_MODES_REVERSE: dict[int, str] = {v: k for k, v in POWER_MODES.items()}

DOLBY_MODES: dict[int, str] = {
    0: "off",
    1: "on_3_zone",
    2: "on_4_zone",
}

# Candidate JSON keys for hardware details that are shown in the web UI's
# "Hardware Details" tab but not in the published API reference.
MAC_KEYS = ("MAC", "Mac", "MacAddress", "MACAddress", "mac_address", "mac")
HW_REV_KEYS = (
    "HardwareRevision",
    "BoardRev",  # documented System/Details field (integer)
    "HardwareVersion",
    "HwRevision",
    "HWRevision",
    "hardware_revision",
    "PCBRevision",
    "Revision",
)
HOSTNAME_KEYS = ("Hostname", "HostName", "hostname", "DeviceName", "Name")

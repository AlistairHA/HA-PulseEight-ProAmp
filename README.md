# Pulse-Eight ProAmp8 for Home Assistant

A custom integration that adds each **Pulse-Eight ProAmp8** 8-zone amplifier to Home Assistant as a **device**. Each device gets system and hardware sensors, plus volume, power mode and mute controls for every output zone. It talks to the amp directly over your LAN through the amp's HTTP/JSON API. No cloud connection is needed.

## What you get (per amplifier)

| Area | Entity | Type |
|---|---|---|
| System info | System status (the full `/System/Details` payload is attached as attributes) | sensor |
| | Dolby mode: Off / On 3-zone / On 4-zone | sensor (enum) |
| | Temperature 1–4 (internal sensors, °C) | sensor |
| | Last boot (worked out from the uptime counter) | sensor (diagnostic) |
| Hardware details | Model, Firmware version, Serial number | sensor (diagnostic) |
| | MAC address, Hardware revision (only if the firmware reports them) | sensor (diagnostic) |
| Per zone ×8 | **Zone N volume**, 0–100 % slider | number |
| | **Zone N power mode**: Off / On / 12V trigger / Auto-sense | select |
| | Zone N mute | switch |
| Maintenance | Restart | button |
| | Status LEDs (front panel; only if the firmware reports it) | switch (config) |

The device page also shows the manufacturer, model, firmware, hardware revision, serial number and MAC, and links to the amp's web UI. If you've named an output in the ProAmp web UI (for example "Kitchen"), that name is added to the entity name, as in `Zone 1 Kitchen volume`.

## Installation

### HACS (recommended)

The contents of this folder must sit at the **root** of the GitHub repository (`hacs.json` and `custom_components/` at the top level, not inside a subfolder). HACS installs from GitHub releases: the included *Release* workflow creates one (for example `v1.1.1`) automatically whenever the `version` in `manifest.json` changes on `main`, and you can also run it by hand from the **Actions** tab. Without a release, HACS shows *"'' is not a usable version"*.
1. Push this folder to a GitHub repository. Then edit `documentation` and `issue_tracker` in `custom_components/pulse_eight_proamp/manifest.json` to point at it.
2. In HACS, open **⋮ → Custom repositories**, add the repository URL and choose type **Integration**.
3. Install **Pulse-Eight ProAmp8**, then restart Home Assistant.

### Manual
Copy `custom_components/pulse_eight_proamp` into `<config>/custom_components/`, then restart Home Assistant.

## Setup
1. Go to **Settings → Devices & services → Add integration → Pulse-Eight ProAmp8**.
2. Enter the amp's IP address. A DHCP reservation is recommended.
3. Repeat for each amplifier. Each amp is identified by its serial number, so adding the same amp twice is rejected.

You can change these later:
- **Configure:** sets the polling interval (default 10 s, range 3–300 s).
- **Reconfigure:** updates the IP address. The amp's serial number is checked so a different unit isn't picked up by mistake.

## API used

| Purpose | Request |
|---|---|
| Model / serial / firmware / status | `GET /System/Details` |
| Temperatures / uptime | `GET /System/Health` |
| Per-zone volume, mute, power mode and names | `GET /Port/List` |
| Dolby mode | `GET /amp/dolbysettings` |
| Set volume | `GET /Amp/Volume/{zone}/{0-100}` |
| Mute / unmute | `GET /Amp/Mute/{zone}/3/{1\|0}` |
| Set power mode | `POST /Amp/StdZone {"zone":z,"power_mode":m}` (falls back to `pwrMode`) |
| Status LEDs | `GET /System/Features`, `POST /System/StatusLED/{on\|off}` |
| Restart | `GET /System/Restart` |

Zones are numbered 0–7 in the API and shown as 1–8 in Home Assistant. These endpoints come from Pulse-Eight's published *ProAmp8 API Function Reference* and their open-source Control4/RTI drivers (github.com/Pulse-Eight/drivers).

The shared MatrixOS endpoints (`/System/*`, `/Port/List`) were also checked against Pulse-Eight's installer API docs (monitoring.pulse-eight.com/APIDocs). Those docs cover the matrix side only. They don't document any `/Amp/*` command, so the amp-specific calls still rely on the function reference and drivers above.

If the amp runs older firmware that leaves volume or power mode out of `/Port/List`, the integration reads them per zone from `/Amp/Volume/{zone}` and `/Amp/StdZone` instead.

## Notes
- **Dolby mode:** In Dolby 3-zone or 4-zone mode, zones 1–3 (or 1–4) carry the surround channels and share a single Dolby volume. Setting the volume on any of those zones changes the volume for the whole surround system.
- **Hardware fields:** The installer API docs give `MAC` and `BoardRev` (an integer board revision) in `/System/Details`, along with an integer `Status` code (0 = healthy). The integration uses those, and still accepts other names such as `HardwareRevision`. If those sensors don't appear, open **System status → Attributes** to see everything the amp reports. You can also use **Download diagnostics** on the device page: it gives the raw API responses with the serial number and MAC redacted. Send that file to whoever maintains this integration so the fields can be mapped.
- **Power mode:** "Off" turns the zone output off. "12V trigger" and "Auto-sense" are the amp's automatic standby modes. Auto-sense isn't supported on the Dolby digital input.

## Development
```bash
pip install pytest-homeassistant-custom-component
pytest
```
The tests run the integration inside Home Assistant against a stateful fake ProAmp8 (`tests/conftest.py`). They cover setup, every platform, the control round-trips, offline and recovery handling, the legacy-firmware fallbacks, and the config, options and reconfigure flows.

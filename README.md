# 💧 HumidiCup H1 BLE

<img src="docs/icon.png" alt="HumidiCup" width="128" align="right">

**Unofficial Bluetooth LE Home Assistant integration for the HumidiCup H1 hygrometer**

Monitor and control your HumidiCup H1 Bluetooth hygrometer locally

## Overview

This integration communicates with the **HumidiCup H1 / H1-B-W** Bluetooth hygrometer
(FCC ID `2A7FR-H1`) over **Bluetooth LE**.

- **Monitor** temperature, humidity, and battery level in real time
- **Control** the buzzer, display unit, alarm thresholds, logging interval, and calibration offsets
- **Integrate** seamlessly with Home Assistant automations
- **Operate** entirely locally — the device protocol is open (no pairing, no PIN, no encryption)

## Supported Devices

**HumidiCup H1** *(H1, H1-B-W)*

*Sensors* | *Switch* | *Select* | *Numbers* | *Buttons*
--- | --- | --- | --- | ---
Temperature | Buzzer | Display unit (°C / °F) | Logging interval | Synchronize clock
Humidity | | | Low / high temperature alarm | Factory reset
Battery | | | Low / high humidity alarm |
| | | | Temperature / humidity calibration offset |

Live telemetry (temperature, humidity, battery, firmware version, buzzer state) is
continuously received from the device's passive BLE broadcasts. The integration connects
on-demand only when applying configuration changes (buzzer, alarms, calibration, clock sync),
leaving the device free to broadcast to Home Assistant and ESPHome Bluetooth proxies.

## Installation

### Prerequisites

- Home Assistant with Bluetooth support (built-in adapter or ESPHome Bluetooth proxy)
- [HACS](https://hacs.xyz/) installed (recommended method)

### Method 1: HACS Installation (Recommended)

**Quick Install:** Click the badge below to open this repository directly in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zuyan9&repository=ha-humidicup-h1-ble&category=integration)

**Manual steps:**

1. Go to **HACS** **Integrations**
2. Click the **⋮** menu, select **Custom repositories**
3. Add this repository URL: `https://github.com/zuyan9/ha-humidicup-h1-ble`
4. Select category: **Integration**, click **Add**
5. Search for **"HumidiCup H1 BLE"** in HACS, click **Download**
6. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/zuyan9/ha-humidicup-h1-ble/releases)
2. Extract the `custom_components/humidicup_h1` folder
3. Copy it to your Home Assistant `config/custom_components/` directory
4. Restart Home Assistant

## Configuration

After installation, the integration automatically discovers HumidiCup H1 devices via
Bluetooth LE. Confirm the discovered device to add it — no credentials are required,
as the device protocol is completely open.

**Options** (via the integration's *Configure* button):

- *Configuration refresh interval* — how often the full device configuration
  (alarms, calibration, unit) is re-read, in minutes (default: 15)
- *Connection timeout* — BLE connection timeout in seconds (default: 20)

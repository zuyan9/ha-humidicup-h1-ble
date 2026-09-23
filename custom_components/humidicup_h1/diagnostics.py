"""Diagnostics support for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import H1ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: H1ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    device = entry.runtime_data
    state = device.state
    return {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "device": {
            "address": device.address,
            "name": device.name,
            "connected": device.connected,
        },
        "state": {
            "temperature": state.temperature,
            "humidity": state.humidity,
            "battery": state.battery,
            "firmware_version": state.firmware_version,
            "buzzer_enabled": state.buzzer_enabled,
            "config": asdict(state.config) if state.config is not None else None,
        },
    }

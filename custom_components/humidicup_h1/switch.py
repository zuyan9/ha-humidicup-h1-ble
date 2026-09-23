"""Switches for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import H1ConfigEntry
from .entity import H1Entity
from .h1lib.device import H1Device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the HumidiCup H1 switches."""
    async_add_entities([H1BuzzerSwitch(entry.runtime_data)])


class H1BuzzerSwitch(H1Entity, SwitchEntity):
    """Buzzer alert switch (opcode 0x07)."""

    _attr_translation_key = "buzzer"

    def __init__(self, device: H1Device) -> None:
        """Initialize the switch."""
        super().__init__(device, "buzzer")

    @property
    def is_on(self) -> bool | None:
        """Return whether the buzzer is enabled."""
        return self._device.state.buzzer_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the buzzer."""
        await self._device.set_buzzer(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the buzzer."""
        await self._device.set_buzzer(False)

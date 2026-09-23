"""Selects for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import H1ConfigEntry
from .entity import H1Entity
from .h1lib.device import H1Device

OPTION_CELSIUS = "celsius"
OPTION_FAHRENHEIT = "fahrenheit"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the HumidiCup H1 selects."""
    async_add_entities([H1UnitSelect(entry.runtime_data)])


class H1UnitSelect(H1Entity, SelectEntity):
    """Display unit select (opcode 0x04)."""

    _attr_translation_key = "temperature_unit"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options: ClassVar[list[str]] = [OPTION_CELSIUS, OPTION_FAHRENHEIT]

    def __init__(self, device: H1Device) -> None:
        """Initialize the select."""
        super().__init__(device, "temperature_unit")

    @property
    def current_option(self) -> str | None:
        """Return the currently configured display unit."""
        config = self._device.state.config
        if config is None:
            return None
        return OPTION_CELSIUS if config.temp_unit_celsius else OPTION_FAHRENHEIT

    async def async_select_option(self, option: str) -> None:
        """Set the display unit."""
        await self._device.set_unit(option == OPTION_CELSIUS)

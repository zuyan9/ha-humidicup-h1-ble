"""Buttons for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
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
    """Set up the HumidiCup H1 buttons."""
    device = entry.runtime_data
    async_add_entities(
        [
            H1SyncTimeButton(device),
            H1FactoryResetButton(device),
        ]
    )


class H1SyncTimeButton(H1Entity, ButtonEntity):
    """Button to synchronize the device RTC with the host clock (opcode 0x01)."""

    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device: H1Device) -> None:
        """Initialize the button."""
        super().__init__(device, "sync_time")

    async def async_press(self) -> None:
        """Synchronize the device clock."""
        await self._device.sync_time()


class H1FactoryResetButton(H1Entity, ButtonEntity):
    """Button to factory reset the device (opcode 0x05). Wipes logged history."""

    _attr_translation_key = "factory_reset"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device: H1Device) -> None:
        """Initialize the button."""
        super().__init__(device, "factory_reset")

    async def async_press(self) -> None:
        """Factory reset the device."""
        await self._device.factory_reset()

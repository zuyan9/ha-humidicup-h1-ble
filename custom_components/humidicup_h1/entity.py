"""Base entity for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .h1lib.device import H1Device


class H1Entity(Entity):
    """Base HumidiCup H1 entity bound to the shared device state."""

    _attr_has_entity_name = True

    def __init__(self, device: H1Device, key: str) -> None:
        """Initialize the entity."""
        self._device = device
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            connections={("bluetooth", device.address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=device.name,
            sw_version=device.state.firmware_version,
        )

    @property
    def available(self) -> bool:
        """Return True if the device is visible over Bluetooth."""
        if self.hass is None:
            return False
        return bluetooth.async_address_present(self.hass, self._device.address)

    async def async_added_to_hass(self) -> None:
        """Subscribe to device state changes."""
        self.async_on_remove(self._device.register_listener(self._handle_state_change))

    def _handle_state_change(self) -> None:
        if self._device.state.firmware_version is not None:
            self._attr_device_info["sw_version"] = self._device.state.firmware_version
        self.async_write_ha_state()

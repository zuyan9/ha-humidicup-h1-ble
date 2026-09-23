"""Base entity for the HumidiCup H1 BLE integration."""

from __future__ import annotations

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
        """Entities are unavailable while the device is disconnected."""
        return self._device.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to device state changes."""
        self.async_on_remove(self._device.register_listener(self._handle_state_change))

    def _handle_state_change(self) -> None:
        self._attr_device_info["sw_version"] = self._device.state.firmware_version
        self.async_write_ha_state()

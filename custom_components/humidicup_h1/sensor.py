"""Sensors for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
    """Set up the HumidiCup H1 sensors."""
    device = entry.runtime_data
    async_add_entities(
        [
            H1TemperatureSensor(device),
            H1HumiditySensor(device),
            H1BatterySensor(device),
        ]
    )


class H1TemperatureSensor(H1Entity, SensorEntity):
    """Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_translation_key = "temperature"

    def __init__(self, device: H1Device) -> None:
        """Initialize the sensor."""
        super().__init__(device, "temperature")

    @property
    def native_value(self) -> float | None:
        """Return the current temperature in Celsius."""
        return self._device.state.temperature


class H1HumiditySensor(H1Entity, SensorEntity):
    """Humidity sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_translation_key = "humidity"

    def __init__(self, device: H1Device) -> None:
        """Initialize the sensor."""
        super().__init__(device, "humidity")

    @property
    def native_value(self) -> float | None:
        """Return the current relative humidity."""
        return self._device.state.humidity


class H1BatterySensor(H1Entity, SensorEntity):
    """Battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "battery"

    def __init__(self, device: H1Device) -> None:
        """Initialize the sensor."""
        super().__init__(device, "battery")

    @property
    def native_value(self) -> int | None:
        """Return the current battery percentage."""
        return self._device.state.battery

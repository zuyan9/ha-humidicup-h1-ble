"""Numbers for the HumidiCup H1 BLE integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import H1ConfigEntry
from .entity import H1Entity
from .h1lib.device import H1Device
from .h1lib.protocol import DeviceConfig


@dataclass(frozen=True, kw_only=True)
class H1NumberEntityDescription(NumberEntityDescription):
    """Describes a HumidiCup H1 number entity."""

    get_value: Callable[[DeviceConfig], float | int | None]
    set_value: Callable[[H1Device, float], Awaitable[None]]


async def _set_interval(device: H1Device, value: float) -> None:
    await device.set_interval(int(value))


async def _set_low_temp_alarm(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_alarms(
        value, config.high_temp_alarm, config.low_humid_alarm, config.high_humid_alarm
    )


async def _set_high_temp_alarm(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_alarms(
        config.low_temp_alarm, value, config.low_humid_alarm, config.high_humid_alarm
    )


async def _set_low_humid_alarm(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_alarms(
        config.low_temp_alarm, config.high_temp_alarm, value, config.high_humid_alarm
    )


async def _set_high_humid_alarm(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_alarms(
        config.low_temp_alarm, config.high_temp_alarm, config.low_humid_alarm, value
    )


async def _set_temp_calibration(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_calibration(value, config.humid_calibration)


async def _set_humid_calibration(device: H1Device, value: float) -> None:
    config = _require_config(device)
    await device.set_calibration(config.temp_calibration, value)


def _require_config(device: H1Device) -> DeviceConfig:
    if device.state.config is None:
        raise RuntimeError("Device configuration not loaded yet")
    return device.state.config


NUMBERS: tuple[H1NumberEntityDescription, ...] = (
    H1NumberEntityDescription(
        key="log_interval",
        translation_key="log_interval",
        native_min_value=1,
        native_max_value=255,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        get_value=lambda config: config.log_interval,
        set_value=_set_interval,
    ),
    H1NumberEntityDescription(
        key="low_temp_alarm",
        translation_key="low_temp_alarm",
        native_min_value=-40,
        native_max_value=85,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        get_value=lambda config: config.low_temp_alarm,
        set_value=_set_low_temp_alarm,
    ),
    H1NumberEntityDescription(
        key="high_temp_alarm",
        translation_key="high_temp_alarm",
        native_min_value=-40,
        native_max_value=85,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        get_value=lambda config: config.high_temp_alarm,
        set_value=_set_high_temp_alarm,
    ),
    H1NumberEntityDescription(
        key="low_humid_alarm",
        translation_key="low_humid_alarm",
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        get_value=lambda config: config.low_humid_alarm,
        set_value=_set_low_humid_alarm,
    ),
    H1NumberEntityDescription(
        key="high_humid_alarm",
        translation_key="high_humid_alarm",
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        get_value=lambda config: config.high_humid_alarm,
        set_value=_set_high_humid_alarm,
    ),
    H1NumberEntityDescription(
        key="temp_calibration",
        translation_key="temp_calibration",
        native_min_value=-25.5,
        native_max_value=25.5,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        get_value=lambda config: config.temp_calibration,
        set_value=_set_temp_calibration,
    ),
    H1NumberEntityDescription(
        key="humid_calibration",
        translation_key="humid_calibration",
        native_min_value=-25.5,
        native_max_value=25.5,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        get_value=lambda config: config.humid_calibration,
        set_value=_set_humid_calibration,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: H1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the HumidiCup H1 numbers."""
    async_add_entities(
        H1Number(entry.runtime_data, description) for description in NUMBERS
    )


class H1Number(H1Entity, NumberEntity):
    """HumidiCup H1 number entity."""

    _attr_entity_category = EntityCategory.CONFIG
    entity_description: H1NumberEntityDescription

    def __init__(
        self, device: H1Device, description: H1NumberEntityDescription
    ) -> None:
        """Initialize the number."""
        super().__init__(device, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        """Return the current value from the device configuration."""
        config = self._device.state.config
        if config is None:
            return None
        return self.entity_description.get_value(config)

    async def async_set_native_value(self, value: float) -> None:
        """Write the value to the device."""
        await self.entity_description.set_value(self._device, value)

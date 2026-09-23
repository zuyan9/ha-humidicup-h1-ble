"""The unofficial HumidiCup H1 BLE integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import (
    CONF_CONNECTION_TIMEOUT,
    DEFAULT_CONNECTION_TIMEOUT,
    DOMAIN,
)
from .h1lib.device import H1Device

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
]

H1ConfigEntry = ConfigEntry[H1Device]

_LOGGER = logging.getLogger(__name__)

ConfigEntryNotReady = partial(ConfigEntryNotReady, translation_domain=DOMAIN)
ConfigEntryError = partial(ConfigEntryError, translation_domain=DOMAIN)

_REAPPEAR_CALLBACKS_KEY = f"{DOMAIN}_reappear_callbacks"


async def async_setup_entry(hass: HomeAssistant, entry: H1ConfigEntry) -> bool:
    """Set up a HumidiCup H1 device from a config entry."""
    address = entry.data.get(CONF_ADDRESS)
    if address is None:
        raise ConfigEntryError(translation_key="missing_address")

    if not bluetooth.async_address_present(hass, address):
        _register_reappear_callback(hass, entry, address)
        raise ConfigEntryNotReady(translation_key="device_not_present")

    _cancel_reappear_callback(hass, entry)

    merged_options = entry.data | entry.options
    timeout = merged_options.get(CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT)

    device: H1Device | None = getattr(entry, "runtime_data", None)
    discovery_info = bluetooth.async_last_service_info(hass, address, connectable=True)

    if device is None:
        if discovery_info is not None:
            ble_dev = discovery_info.device
        else:
            ble_dev = bluetooth.async_ble_device_from_address(
                hass, address, connectable=True
            )
        if ble_dev is None:
            _register_reappear_callback(hass, entry, address)
            raise ConfigEntryNotReady(translation_key="device_not_present")

        device = H1Device(
            ble_dev,
            local_name=entry.data.get("local_name"),
        )
        entry.runtime_data = device
    elif discovery_info is not None:
        device.update_ble_device(discovery_info.device)

    # Prime device state from latest advertisement if available
    if discovery_info is not None:
        for (
            manufacturer_data
        ) in discovery_info.advertisement.manufacturer_data.values():
            if len(manufacturer_data) >= 15 and manufacturer_data[6] == 0x01:
                device.feed_advertisement(manufacturer_data)
                break

    # Read initial configuration and sync time via a brief on-demand connection
    try:
        async with asyncio.timeout(timeout * 2):
            async with device.connection(timeout=timeout):
                await device.sync_time()
                await device.read_config()
    except (ConnectionError, BleakError, TimeoutError) as err:
        _LOGGER.warning(
            "Initial GATT handshake failed for %s (%s); continuing in passive mode",
            address,
            err,
        )
    except Exception as err:
        _LOGGER.warning(
            "Unexpected error during initial GATT handshake with %s: %s",
            address,
            err,
        )

    # Register passive advertisement listener for continuous telemetry updates
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _advertisement_callback(device),
            BluetoothCallbackMatcher(address=address),
            BluetoothScanningMode.PASSIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def _update_listener(hass: HomeAssistant, entry: H1ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: H1ConfigEntry) -> bool:
    """Unload a config entry."""
    _cancel_reappear_callback(hass, entry)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        try:
            await entry.runtime_data.disconnect()
        except Exception:
            _LOGGER.exception("Error disconnecting device during unload, continuing")
    return unload_ok


def _advertisement_callback(
    device: H1Device,
) -> Callable[[BluetoothServiceInfoBleak, BluetoothChange], None]:
    @callback
    def _on_advertisement(
        service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        device.update_ble_device(service_info.device)
        for manufacturer_data in service_info.advertisement.manufacturer_data.values():
            if len(manufacturer_data) >= 15 and manufacturer_data[6] == 0x01:
                device.feed_advertisement(manufacturer_data)
                break

    return _on_advertisement


def _register_reappear_callback(
    hass: HomeAssistant, entry: ConfigEntry, address: str
) -> None:
    callbacks: dict[str, Callable] = hass.data.setdefault(_REAPPEAR_CALLBACKS_KEY, {})

    if entry.entry_id in callbacks:
        return

    def _on_device_reappear(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        _LOGGER.info(
            "Device %s reappeared via BLE advertisement, scheduling reload",
            address,
        )
        _cancel_reappear_callback(hass, entry)
        hass.config_entries.async_schedule_reload(entry.entry_id)

    cancel = bluetooth.async_register_callback(
        hass,
        _on_device_reappear,
        BluetoothCallbackMatcher(address=address, connectable=True),
        BluetoothScanningMode.PASSIVE,
    )
    callbacks[entry.entry_id] = cancel


def _cancel_reappear_callback(hass: HomeAssistant, entry: ConfigEntry) -> None:
    callbacks: dict[str, Callable] = hass.data.get(_REAPPEAR_CALLBACKS_KEY, {})
    if cancel := callbacks.pop(entry.entry_id, None):
        cancel()

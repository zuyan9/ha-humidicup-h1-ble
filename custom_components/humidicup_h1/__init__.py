"""The unofficial HumidiCup H1 BLE integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
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
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CONNECTION_TIMEOUT,
    CONF_UPDATE_PERIOD,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_UPDATE_PERIOD,
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

type H1ConfigEntry = ConfigEntry[H1Device]

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
    update_period = merged_options.get(CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD)

    device: H1Device | None = getattr(entry, "runtime_data", None)
    discovery_info = bluetooth.async_last_service_info(hass, address, connectable=True)

    if device is None:
        device = H1Device(
            discovery_info.device,
            local_name=entry.data.get("local_name"),
        )
        entry.runtime_data = device
    elif discovery_info is not None:
        device.update_ble_device(discovery_info.device)

    try:
        async with asyncio.timeout(timeout * 3):
            await device.connect(timeout=timeout)
    except (ConnectionError, BleakError, TimeoutError) as err:
        await device.disconnect()
        raise ConfigEntryNotReady(
            translation_key="could_not_connect",
            translation_placeholders={"error": str(err)},
        ) from err
    except Exception as err:
        await device.disconnect()
        _LOGGER.exception("Unknown error connecting to %s", address)
        raise ConfigEntryNotReady(
            translation_key="unknown_error",
            translation_placeholders={"error": str(err)},
        ) from err

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _advertisement_callback(device),
            BluetoothCallbackMatcher(address=address),
            BluetoothScanningMode.PASSIVE,
        )
    )

    @callback
    def _periodic_config_refresh(now) -> None:
        if device.connected:
            hass.async_create_task(_safe_read_config(device))

    entry.async_on_unload(
        async_track_time_interval(
            hass, _periodic_config_refresh, timedelta(minutes=update_period)
        )
    )

    @callback
    def _on_unexpected_disconnect() -> None:
        _LOGGER.info("Device %s disconnected unexpectedly, reloading entry", address)
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        device.register_disconnect_callback(_on_unexpected_disconnect)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def _safe_read_config(device: H1Device) -> None:
    try:
        await device.read_config()
    except Exception:
        _LOGGER.debug("Periodic config read failed for %s", device.address)


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

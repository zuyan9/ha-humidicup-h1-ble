"""Config flow for the HumidiCup H1 BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_PUSH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_CONNECTION_TIMEOUT,
    CONF_UPDATE_PERIOD,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_UPDATE_PERIOD,
    DOMAIN,
)
from .h1lib.device import H1Device
from .h1lib.protocol import DEVICE_MODEL_TYPE, MANUFACTURER_ID

_LOGGER = logging.getLogger(__name__)


def _is_h1_advertisement(service_info: BluetoothServiceInfoBleak) -> bool:
    data = service_info.advertisement.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < 15 or data[6] != DEVICE_MODEL_TYPE:
        return False
    mac = bytes.fromhex(service_info.address.replace(":", ""))
    return bytes(data[0:6]) == mac[::-1]


class H1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """HumidiCup H1 config flow."""

    VERSION = 1
    MINOR_VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_h1_advertisement(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        if user_input is not None:
            errors = await self._async_validate_device(self._discovery_info)
            if not errors:
                return self._create_entry_from_discovery(self._discovery_info)
            return self.async_abort(reason=errors["base"])

        name = self._discovery_info.advertisement.local_name or "HumidiCup H1"
        title = f"{name} ({self._discovery_info.address})"
        self.context["title_placeholders"] = {"name": title}
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": title},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick a discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            errors = await self._async_validate_device(discovery_info)
            if not errors:
                return self._create_entry_from_discovery(discovery_info)
            return self.async_show_form(
                step_id="user",
                data_schema=self._devices_schema(),
                errors=errors,
            )

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if _is_h1_advertisement(discovery_info):
                self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(step_id="user", data_schema=self._devices_schema())

    def _devices_schema(self) -> vol.Schema:
        devices = {
            address: f"{info.advertisement.local_name or 'HumidiCup H1'} ({address})"
            for address, info in self._discovered_devices.items()
        }
        return vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)})

    async def _async_validate_device(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> dict[str, str]:
        """Test the connection by connecting and reading the device config."""
        device = H1Device(
            discovery_info.device,
            local_name=discovery_info.advertisement.local_name,
        )
        try:
            async with device.connection(timeout=DEFAULT_CONNECTION_TIMEOUT):
                await device.read_config()
        except Exception:
            _LOGGER.debug(
                "Validation connection to %s failed",
                discovery_info.address,
                exc_info=True,
            )
            return {"base": "cannot_connect"}
        return {}

    @callback
    def _create_entry_from_discovery(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        name = discovery_info.advertisement.local_name or "HumidiCup H1"
        return self.async_create_entry(
            title=name,
            data={
                CONF_ADDRESS: discovery_info.address,
                "local_name": name,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Create the options flow."""
        return H1OptionsFlowHandler()


class H1OptionsFlowHandler(OptionsFlow):
    """HumidiCup H1 options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        merged = self.config_entry.data | self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_UPDATE_PERIOD): vol.All(
                            int, vol.Range(min=1, max=1440)
                        ),
                        vol.Required(CONF_CONNECTION_TIMEOUT): vol.All(
                            int, vol.Range(min=5, max=120)
                        ),
                    }
                ),
                {
                    CONF_UPDATE_PERIOD: merged.get(
                        CONF_UPDATE_PERIOD, DEFAULT_UPDATE_PERIOD
                    ),
                    CONF_CONNECTION_TIMEOUT: merged.get(
                        CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT
                    ),
                },
            ),
        )

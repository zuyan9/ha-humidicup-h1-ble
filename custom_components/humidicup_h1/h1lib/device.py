"""HumidiCup H1 BLE device connection and state management."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from . import protocol
from .protocol import AdvertisementData, DeviceConfig

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
MAX_CONNECT_ATTEMPTS = 3


@dataclass
class H1State:
    """Merged device state from advertisements and the 0x8E config read."""

    temperature: float | None = None
    humidity: float | None = None
    battery: int | None = None
    firmware_version: str | None = None
    buzzer_enabled: bool | None = None
    config: DeviceConfig | None = None


class AsyncRLock:
    """Reentrant asyncio lock bound to the current asyncio.Task."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0

    async def acquire(self) -> None:
        current_task = asyncio.current_task()
        if self._owner is not None and self._owner == current_task:
            self._depth += 1
            return
        await self._lock.acquire()
        self._owner = current_task
        self._depth = 1

    def release(self) -> None:
        current_task = asyncio.current_task()
        if self._owner != current_task:
            raise RuntimeError("Cannot release un-acquired lock")
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        self.release()


class H1Device:
    """HumidiCup H1 device supporting passive telemetry and on-demand control."""

    def __init__(self, ble_device: BLEDevice, local_name: str | None = None) -> None:
        """Initialize the device wrapper."""
        self.ble_device = ble_device
        self.name = local_name or ble_device.name or "HumidiCup H1"
        self.state = H1State()
        self.last_seen: float | None = None
        self._client: BleakClient | None = None
        self._expected_disconnect = False
        self._pending: dict[int, asyncio.Future[bytes]] = {}
        self._listeners: list[Callable[[], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._command_lock = asyncio.Lock()
        self._connect_lock = AsyncRLock()

    @property
    def address(self) -> str:
        """Device MAC/address."""
        return self.ble_device.address

    @property
    def connected(self) -> bool:
        """Whether the GATT connection is currently up."""
        return self._client is not None and self._client.is_connected

    def update_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice reference (e.g. after adapter switch or new adv)."""
        self.ble_device = ble_device

    def feed_advertisement(self, data: bytes) -> None:
        """Merge passive advertisement telemetry into the state."""
        try:
            adv: AdvertisementData = protocol.decode_advertisement(data)
        except protocol.ProtocolError:
            _LOGGER.debug("Ignoring malformed advertisement from %s", self.address)
            return
        if adv.model_type != protocol.DEVICE_MODEL_TYPE:
            return
        self.last_seen = time.time()
        self.state.temperature = adv.temperature
        self.state.humidity = adv.humidity
        self.state.battery = adv.battery
        self.state.firmware_version = adv.firmware_version
        self.state.buzzer_enabled = adv.buzzer_enabled
        self._notify_listeners()

    @asynccontextmanager
    async def connection(self, timeout: float = DEFAULT_TIMEOUT) -> AsyncIterator[None]:
        """Context manager to ensure GATT connection during control operations."""
        async with self._connect_lock:
            was_connected = self.connected
            if not was_connected:
                await self.connect(timeout=timeout)
            try:
                yield
            finally:
                if not was_connected:
                    await self.disconnect()

    async def connect(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Connect and subscribe to notifications."""
        if self.connected:
            return
        self._expected_disconnect = False
        last_exc: Exception | None = None
        for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
            try:
                _LOGGER.debug(
                    "Connecting to %s (attempt %d/%d)",
                    self.address,
                    attempt,
                    MAX_CONNECT_ATTEMPTS,
                )
                self._client = await establish_connection(
                    BleakClient,
                    self.ble_device,
                    self.name,
                    disconnected_callback=self._on_disconnected,
                    timeout=timeout,
                )
                await self._client.start_notify(
                    protocol.NOTIFY_CHAR_UUID, self._notification_handler
                )
                break
            except (BleakError, TimeoutError) as exc:
                last_exc = exc
                _LOGGER.debug(
                    "Connection attempt %d to %s failed: %s", attempt, self.address, exc
                )
                await asyncio.sleep(min(2 * attempt, 5))
        else:
            raise ConnectionError(
                f"Could not connect to {self.address} after "
                f"{MAX_CONNECT_ATTEMPTS} attempts: {last_exc}"
            )

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._expected_disconnect = True
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        client, self._client = self._client, None
        if client is not None:
            try:
                if client.is_connected:
                    await client.stop_notify(protocol.NOTIFY_CHAR_UUID)
                    await client.disconnect()
            except BleakError:
                _LOGGER.debug("Error during disconnect from %s", self.address)

    async def sync_time(self) -> None:
        """Command 0x01: synchronize the device RTC with the host clock."""
        async with self.connection():
            await self._execute(protocol.OP_TIME_SYNC, protocol.build_time_sync())

    async def read_config(self) -> DeviceConfig:
        """Command 0x0E01: read and store the full device configuration."""
        async with self.connection():
            response = await self._execute(
                protocol.OP_READ_CONFIG, protocol.build_read_config()
            )
        config = protocol.decode_config(response)
        self.state.config = config
        self.state.buzzer_enabled = config.buzzer_enabled
        self._notify_listeners()
        return config

    async def set_unit(self, celsius: bool) -> None:
        """Command 0x04: set the display unit."""
        async with self.connection():
            await self._execute(protocol.OP_SET_UNIT, protocol.build_set_unit(celsius))
        if self.state.config is not None:
            self.state.config.temp_unit_celsius = celsius
        self._notify_listeners()

    async def set_buzzer(self, enabled: bool) -> None:
        """Command 0x07: toggle the buzzer."""
        async with self.connection():
            await self._execute(
                protocol.OP_SET_BUZZER, protocol.build_set_buzzer(enabled)
            )
        self.state.buzzer_enabled = enabled
        if self.state.config is not None:
            self.state.config.buzzer_enabled = enabled
        self._notify_listeners()

    async def set_interval(self, minutes: int) -> None:
        """Command 0x09: set the logging interval in minutes."""
        async with self.connection():
            await self._execute(
                protocol.OP_SET_INTERVAL, protocol.build_set_interval(minutes)
            )
        if self.state.config is not None:
            self.state.config.log_interval = minutes
        self._notify_listeners()

    async def set_alarms(
        self,
        low_temp: float,
        high_temp: float,
        low_humid: float,
        high_humid: float,
    ) -> None:
        """Command 0x06: set the alarm thresholds."""
        async with self.connection():
            await self._execute(
                protocol.OP_SET_ALARMS,
                protocol.build_set_alarms(low_temp, high_temp, low_humid, high_humid),
            )
        if self.state.config is not None:
            self.state.config.low_temp_alarm = low_temp
            self.state.config.high_temp_alarm = high_temp
            self.state.config.low_humid_alarm = low_humid
            self.state.config.high_humid_alarm = high_humid
        self._notify_listeners()

    async def set_calibration(self, temp_offset: float, humid_offset: float) -> None:
        """Command 0x0A: set manual calibration offsets."""
        async with self.connection():
            await self._execute(
                protocol.OP_SET_CALIBRATION,
                protocol.build_set_calibration(temp_offset, humid_offset),
            )
        if self.state.config is not None:
            self.state.config.temp_calibration = temp_offset
            self.state.config.humid_calibration = humid_offset
        self._notify_listeners()

    async def factory_reset(self) -> None:
        """Command 0x05: factory reset the device."""
        async with self.connection():
            await self._execute(
                protocol.OP_FACTORY_RESET, protocol.build_factory_reset()
            )

    async def _execute(
        self, opcode: int, payload: bytes, timeout: float = 10.0
    ) -> bytes:
        """Write a command and await its matching 0x80|opcode response."""
        if self._client is None or not self._client.is_connected:
            raise ConnectionError(f"Not connected to {self.address}")
        async with self._command_lock:
            loop = asyncio.get_running_loop()
            future: asyncio.Future[bytes] = loop.create_future()
            self._pending[protocol.response_opcode(opcode)] = future
            try:
                await self._client.write_gatt_char(
                    protocol.WRITE_CHAR_UUID, payload, response=True
                )
                return await asyncio.wait_for(future, timeout)
            finally:
                self._pending.pop(protocol.response_opcode(opcode), None)

    def _notification_handler(self, _: int, data: bytearray) -> None:
        """Dispatch an AA01 notification to the pending command or config parser."""
        if not data:
            return
        opcode = data[0]
        _LOGGER.debug("Notification from %s: %s", self.address, data.hex())
        future = self._pending.get(opcode)
        if future is not None and not future.done():
            try:
                if opcode != protocol.response_opcode(protocol.OP_READ_CONFIG):
                    protocol.check_response(bytes(data), opcode & 0x7F)
                future.set_result(bytes(data))
            except protocol.ProtocolError as exc:
                future.set_exception(exc)

    def _on_disconnected(self, client: BleakClient) -> None:
        """Handle an unexpected disconnect."""
        _LOGGER.debug("Disconnected from %s", self.address)
        self._client = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError(f"Disconnected from {self.address}"))
        self._pending.clear()
        self._notify_listeners()
        if not self._expected_disconnect:
            for callback in self._disconnect_callbacks:
                callback()

    def register_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a state-change listener; returns an unsubscribe callable."""
        self._listeners.append(callback)

        def _unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _unsubscribe

    def register_disconnect_callback(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register an unexpected-disconnect callback; returns unsubscribe."""
        self._disconnect_callbacks.append(callback)

        def _unsubscribe() -> None:
            if callback in self._disconnect_callbacks:
                self._disconnect_callbacks.remove(callback)

        return _unsubscribe

    def _notify_listeners(self) -> None:
        for callback in self._listeners:
            callback()

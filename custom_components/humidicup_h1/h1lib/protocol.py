"""HumidiCup H1 BLE protocol packet builders and parsers.

Protocol reference:
https://github.com/zuyan9/HumidiCup_H1_Firmware_Research/blob/main/docs/ble_protocol.md
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

SERVICE_UUID = "0000aa00-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000aa02-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000aa01-0000-1000-8000-00805f9b34fb"

DEVICE_MODEL_TYPE = 0x01
MANUFACTURER_ID = 0x0001

OP_TIME_SYNC = 0x01
OP_READ_HISTORY = 0x03
OP_SET_UNIT = 0x04
OP_FACTORY_RESET = 0x05
OP_SET_ALARMS = 0x06
OP_SET_BUZZER = 0x07
OP_SET_INTERVAL = 0x09
OP_SET_CALIBRATION = 0x0A
OP_READ_CONFIG = 0x0E

UNIT_FAHRENHEIT = 0x00
UNIT_CELSIUS = 0x01


class ProtocolError(Exception):
    """Malformed or unexpected packet."""


@dataclass
class AdvertisementData:
    """Telemetry parsed from the passive BLE advertisement manufacturer data."""

    model_type: int
    battery: int
    temperature: float
    humidity: float
    firmware_version: str
    buzzer_enabled: bool


@dataclass
class DeviceConfig:
    """Device configuration parsed from the 0x8E response packet."""

    temp_unit_celsius: bool
    buzzer_enabled: bool
    log_interval: int
    temp_calibration: float
    humid_calibration: float
    low_temp_alarm: float
    high_temp_alarm: float
    low_humid_alarm: float
    high_humid_alarm: float


def decode_advertisement(data: bytes) -> AdvertisementData:
    """Decode the advertisement manufacturer data payload (>= 15 bytes)."""
    if len(data) < 15:
        raise ProtocolError(
            f"Advertisement payload too short: {len(data)} bytes (expected >= 15)"
        )
    temperature_raw = struct.unpack("<h", data[8:10])[0]
    humidity_raw = struct.unpack("<h", data[10:12])[0]
    return AdvertisementData(
        model_type=data[6],
        battery=data[7],
        temperature=temperature_raw / 10.0,
        humidity=humidity_raw / 10.0,
        firmware_version=f"V{data[13]}.{data[12]}",
        buzzer_enabled=bool(data[14]),
    )


def decode_config(data: bytes) -> DeviceConfig:
    """Decode the 19-byte 0x8E device configuration response."""
    if len(data) < 19 or data[0] != (OP_READ_CONFIG | 0x80):
        raise ProtocolError("Invalid 0x8E config packet")

    def _signed(magnitude: int, negative: int) -> int:
        return -magnitude if negative else magnitude

    return DeviceConfig(
        temp_unit_celsius=bool(data[1]),
        buzzer_enabled=bool(data[2]),
        log_interval=data[3],
        temp_calibration=_signed(data[5], data[4]) / 10.0,
        humid_calibration=_signed(data[7], data[6]) / 10.0,
        low_temp_alarm=_signed(struct.unpack("<h", data[11:13])[0], data[10]) / 10.0,
        high_temp_alarm=struct.unpack("<h", data[13:15])[0] / 10.0,
        low_humid_alarm=struct.unpack("<h", data[15:17])[0] / 10.0,
        high_humid_alarm=struct.unpack("<h", data[17:19])[0] / 10.0,
    )


def build_time_sync(timestamp: int | None = None) -> bytes:
    """Command 0x01: synchronize the RTC clock with a Unix epoch timestamp."""
    return bytes([OP_TIME_SYNC]) + struct.pack(
        "<I", timestamp if timestamp is not None else int(time.time())
    )


def build_set_unit(celsius: bool) -> bytes:
    """Command 0x04: set the display unit."""
    return bytes([OP_SET_UNIT, UNIT_CELSIUS if celsius else UNIT_FAHRENHEIT])


def build_factory_reset() -> bytes:
    """Command 0x05: factory reset."""
    return bytes([OP_FACTORY_RESET])


def build_set_buzzer(enabled: bool) -> bytes:
    """Command 0x07: toggle the buzzer."""
    return bytes([OP_SET_BUZZER, 0x01 if enabled else 0x00])


def build_set_interval(minutes: int) -> bytes:
    """Command 0x09: set the logging interval in minutes."""
    if not 10 <= minutes <= 60:
        raise ValueError("Interval must be within 10..60 minutes (firmware-enforced)")
    return bytes([OP_SET_INTERVAL, minutes])


def build_set_alarms(
    low_temp: float,
    high_temp: float,
    low_humid: float,
    high_humid: float,
) -> bytes:
    """Command 0x06: set the temperature/humidity alarm bounds (values x10)."""
    negative = low_temp < 0
    return bytes([OP_SET_ALARMS, 0x01 if negative else 0x00]) + struct.pack(
        "<HHHH",
        round(abs(low_temp) * 10),
        round(abs(high_temp) * 10),
        round(abs(low_humid) * 10),
        round(abs(high_humid) * 10),
    )


def build_set_calibration(temp_offset: float, humid_offset: float) -> bytes:
    """Command 0x0A: set manual calibration offsets (magnitude x10 per axis)."""
    return bytes(
        [
            OP_SET_CALIBRATION,
            0x01 if temp_offset < 0 else 0x00,
            round(abs(temp_offset) * 10),
            0x01 if humid_offset < 0 else 0x00,
            round(abs(humid_offset) * 10),
        ]
    )


def build_read_config() -> bytes:
    """Command 0x0E01: query the full device configuration."""
    return bytes([OP_READ_CONFIG, 0x01])


def response_opcode(request_opcode: int) -> int:
    """Expected response opcode for a request opcode."""
    return request_opcode | 0x80


def check_response(data: bytes, request_opcode: int) -> None:
    """Validate a response packet's opcode and SUCCESS status."""
    if len(data) < 3:
        raise ProtocolError(f"Response too short: {len(data)} bytes")
    expected = response_opcode(request_opcode)
    if data[0] != expected:
        raise ProtocolError(
            f"Unexpected response opcode 0x{data[0]:02X} (want 0x{expected:02X})"
        )
    if data[1] != 0x00 or data[2] != 0x00:
        raise ProtocolError(
            f"Device returned error status 0x{data[1]:02X} 0x{data[2]:02X}"
        )

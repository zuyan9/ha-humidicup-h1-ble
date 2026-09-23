"""Unit tests for the HumidiCup H1 device wrapper."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.backends.device import BLEDevice

from custom_components.humidicup_h1.h1lib.device import H1Device


@pytest.fixture
def mock_ble_device() -> BLEDevice:
    dev = MagicMock(spec=BLEDevice)
    dev.address = "62:00:A5:00:13:3F"
    dev.name = "H1"
    return dev


def test_feed_advertisement(mock_ble_device: BLEDevice):
    device = H1Device(mock_ble_device)
    raw = bytes([0x00] * 6 + [0x01, 85, 0xFC, 0x00, 0x6E, 0x02, 5, 3, 1])
    listener_called = False

    def listener():
        nonlocal listener_called
        listener_called = True

    device.register_listener(listener)
    device.feed_advertisement(raw)

    assert listener_called is True
    assert device.state.temperature == pytest.approx(25.2)
    assert device.state.humidity == pytest.approx(62.2)
    assert device.state.battery == 85
    assert device.state.firmware_version == "V3.5"
    assert device.state.buzzer_enabled is True
    assert device.last_seen is not None


@pytest.mark.asyncio
async def test_on_demand_connection_lifecycle(mock_ble_device: BLEDevice):
    device = H1Device(mock_ble_device)

    fake_client = MagicMock()
    fake_client.is_connected = True

    async def fake_connect(timeout=20.0):
        device._client = fake_client

    async def fake_disconnect():
        device._client = None

    device.connect = AsyncMock(side_effect=fake_connect)
    device.disconnect = AsyncMock(side_effect=fake_disconnect)

    # Standalone connection block
    async with device.connection():
        # Inside context, connect was called once and device is connected
        assert device.connect.await_count == 1
        assert device.connected is True
        assert device.disconnect.await_count == 0

        # Nested connection block reuses connection without reconnecting
        async with device.connection():
            assert device.connect.await_count == 1
            assert device.disconnect.await_count == 0

    # Once outer context exits, disconnect was called
    assert device.disconnect.await_count == 1
    assert device.connected is False

"""Unit tests for the HumidiCup H1 protocol library."""

import struct

import pytest

from custom_components.humidicup_h1.h1lib import protocol


def test_decode_advertisement_sample_vector():
    raw = bytes([0x00] * 6 + [0x01, 85, 0xFC, 0x00, 0x6E, 0x02, 5, 3, 1])
    adv = protocol.decode_advertisement(raw)
    assert adv.model_type == 0x01
    assert adv.battery == 85
    assert adv.temperature == pytest.approx(25.2)
    assert adv.humidity == pytest.approx(62.2)
    assert adv.firmware_version == "V3.5"
    assert adv.buzzer_enabled is True


def test_decode_advertisement_negative_temperature():
    raw = bytearray(15)
    raw[6] = 0x01
    raw[7] = 42
    raw[8:10] = struct.pack("<h", -105)
    raw[10:12] = struct.pack("<h", 330)
    raw[12] = 0
    raw[13] = 3
    raw[14] = 0
    adv = protocol.decode_advertisement(bytes(raw))
    assert adv.temperature == pytest.approx(-10.5)
    assert adv.humidity == pytest.approx(33.0)
    assert adv.buzzer_enabled is False


def test_decode_advertisement_too_short():
    with pytest.raises(protocol.ProtocolError):
        protocol.decode_advertisement(bytes(14))


def test_decode_config_sample():
    raw = bytes(
        [
            0x8E,
            0x01,  # unit C
            0x01,  # beep on
            0x0A,  # interval 10
            0x01,  # temp cal neg
            0x14,  # temp cal 2.0
            0x00,  # humid cal pos
            0x1E,  # humid cal 3.0
            0x00,
            0x00,
            0x01,  # low temp neg
        ]
    ) + struct.pack("<hhhh", 50, 350, 200, 800)
    cfg = protocol.decode_config(raw)
    assert cfg.temp_unit_celsius is True
    assert cfg.buzzer_enabled is True
    assert cfg.log_interval == 10
    assert cfg.temp_calibration == pytest.approx(-2.0)
    assert cfg.humid_calibration == pytest.approx(3.0)
    assert cfg.low_temp_alarm == pytest.approx(-5.0)
    assert cfg.high_temp_alarm == pytest.approx(35.0)
    assert cfg.low_humid_alarm == pytest.approx(20.0)
    assert cfg.high_humid_alarm == pytest.approx(80.0)


def test_decode_config_rejects_bad_opcode():
    with pytest.raises(protocol.ProtocolError):
        protocol.decode_config(bytes([0x83] + [0] * 18))


def test_build_time_sync():
    packet = protocol.build_time_sync(1708262528)
    assert packet == bytes([0x01]) + struct.pack("<I", 1708262528)
    assert len(protocol.build_time_sync()) == 5


def test_build_set_unit():
    assert protocol.build_set_unit(True) == bytes([0x04, 0x01])
    assert protocol.build_set_unit(False) == bytes([0x04, 0x00])


def test_build_factory_reset():
    assert protocol.build_factory_reset() == bytes([0x05])


def test_build_set_buzzer():
    assert protocol.build_set_buzzer(True) == bytes([0x07, 0x01])
    assert protocol.build_set_buzzer(False) == bytes([0x07, 0x00])


def test_build_set_interval():
    assert protocol.build_set_interval(10) == bytes([0x09, 0x0A])
    with pytest.raises(ValueError):
        protocol.build_set_interval(0)


def test_build_set_alarms_positive():
    packet = protocol.build_set_alarms(5.0, 35.0, 20.0, 80.0)
    assert packet == bytes([0x06, 0x00]) + struct.pack("<HHHH", 50, 350, 200, 800)


def test_build_set_alarms_negative_low_temp():
    packet = protocol.build_set_alarms(-5.0, 35.0, 20.0, 80.0)
    assert packet == bytes([0x06, 0x01]) + struct.pack("<HHHH", 50, 350, 200, 800)


def test_build_set_calibration():
    assert protocol.build_set_calibration(-2.0, 3.0) == bytes(
        [0x0A, 0x01, 20, 0x00, 30]
    )
    assert protocol.build_set_calibration(1.5, -0.5) == bytes([0x0A, 0x00, 15, 0x01, 5])


def test_build_read_config():
    assert protocol.build_read_config() == bytes([0x0E, 0x01])


def test_check_response_ok():
    protocol.check_response(bytes([0x81, 0x00, 0x00]), protocol.OP_TIME_SYNC)


def test_check_response_wrong_opcode():
    with pytest.raises(protocol.ProtocolError):
        protocol.check_response(bytes([0x84, 0x00, 0x00]), protocol.OP_TIME_SYNC)


def test_check_response_error_status():
    with pytest.raises(protocol.ProtocolError):
        protocol.check_response(bytes([0x81, 0x01, 0x00]), protocol.OP_TIME_SYNC)

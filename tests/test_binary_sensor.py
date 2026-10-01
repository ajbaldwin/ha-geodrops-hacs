from dataclasses import replace

import pytest

from custom_components.geodrops.binary_sensor import build_binary_sensors
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from .test_sensor import _coord, _reading

DEVICE = {"serial": "AAA111", "device_id": 1001, "name": "Front"}


def _binary_sensor(reading, key):
    sensors = build_binary_sensors(_coord(reading), DEVICE)
    return {s.entity_description.key: s for s in sensors}[key]


def _battery_status(reading):
    return _binary_sensor(reading, "battery_poor")


def test_four_binary_sensors_per_device():
    assert len(build_binary_sensors(_coord(_reading()), DEVICE)) == 4


def test_every_binary_sensor_is_a_diagnostic_problem():
    for sensor in build_binary_sensors(_coord(_reading()), DEVICE):
        assert sensor.device_class is BinarySensorDeviceClass.PROBLEM
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC
        assert sensor.entity_registry_enabled_default


def test_battery_status_follows_geodrops_flag():
    sensor = _battery_status(replace(_reading(), battery_poor=True))
    assert sensor.is_on is True
    assert sensor.unique_id == "AAA111_battery_poor"  # unchanged by the rename
    assert sensor.translation_key == "battery_status"
    assert _battery_status(replace(_reading(), battery_poor=False)).is_on is False


def test_battery_status_is_unknown_without_a_value():
    assert _battery_status(replace(_reading(), battery_poor=None)).is_on is None
    assert _battery_status(None).is_on is None


@pytest.mark.parametrize(
    ("codes", "on"),
    [
        ({"ATT_DW_NEW"}, {"max_moisture_required"}),
        ({"DW_RENEW", "DW_M_LOW12"}, {"wick_renewal"}),
        ({"CHK_M_HWR"}, {"hardware_problem"}),
        ({"ERR_LOSS"}, {"hardware_problem"}),
        ({"ATT_DW_NEW", "NULL_HWR"}, {"max_moisture_required", "hardware_problem"}),
        ({"DW_M_LOW3", "LAX_M_EVA12", "ATT_SS_NEW"}, set()),
        (set(), set()),
    ],
)
def test_next_action_problems(codes, on):
    reading = replace(_reading(), next_action=frozenset(codes))
    for key in ("max_moisture_required", "wick_renewal", "hardware_problem"):
        assert _binary_sensor(reading, key).is_on is (key in on)


def test_next_action_problems_are_unknown_without_the_column():
    reading = replace(_reading(), next_action=None)
    for key in ("max_moisture_required", "wick_renewal", "hardware_problem"):
        assert _binary_sensor(reading, key).is_on is None

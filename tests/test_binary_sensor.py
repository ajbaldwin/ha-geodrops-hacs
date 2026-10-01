from dataclasses import replace

from custom_components.geodrops.binary_sensor import build_binary_sensors
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from .test_sensor import _coord, _reading

DEVICE = {"serial": "AAA111", "device_id": 1001, "name": "Front"}


def _battery_problem(reading):
    (sensor,) = build_binary_sensors(_coord(reading), DEVICE)
    return sensor


def test_battery_problem_follows_geodrops_flag():
    sensor = _battery_problem(replace(_reading(), battery_poor=True))
    assert sensor.is_on is True
    assert sensor.unique_id == "AAA111_battery_poor"
    assert sensor.device_class is BinarySensorDeviceClass.PROBLEM
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC
    assert sensor.entity_registry_enabled_default
    assert _battery_problem(replace(_reading(), battery_poor=False)).is_on is False


def test_battery_problem_is_unknown_without_a_value():
    assert _battery_problem(replace(_reading(), battery_poor=None)).is_on is None
    assert _battery_problem(None).is_on is None

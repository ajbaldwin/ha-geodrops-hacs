import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from homeassistant.util import dt as dt_util
from custom_components.geodrops.sensor import build_sensors, SENSOR_SPECS
from custom_components.geodrops.transform import DeviceReading
from custom_components.geodrops import const


def _reading(all_training=False):
    q = -1 if all_training else 2
    return DeviceReading(device_id=1001, sync_delay_hours=2.0, moisture_index=3,
                         moisture_pct=42.5, moisture_d1=40.0, moisture_d2=41.0, moisture_d3=42.0,
                         temp_surface=19.0, temp_d1=18.0, temp_d2=17.0, temp_d3=16.0,
                         battery_pct=88.0, sun_7d=6.0, qcn_d1=q, qcn_d2=q, qcn_d3=q)


def _coord(reading, skip_hours=12, last_success_time=None):
    c = MagicMock()
    c.reading.return_value = reading
    c.entry.options = {const.CONF_SKIP_HOURS: skip_hours}
    # default: the feed just succeeded, so tests that don't care about
    # FIX 8's expire_after_minutes wiring stay within the window
    c.last_success_time = last_success_time if last_success_time is not None else dt_util.utcnow()
    return c


def test_15_sensors_per_device():
    assert len(SENSOR_SPECS) == 15


def test_moisture_value_and_state():
    coord = _coord(_reading())
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    by_suffix = {s._suffix: s for s in sensors}
    assert by_suffix["moisture"].native_value == 42.5
    assert by_suffix["moisture_state"].native_value == "Moist+"
    assert by_suffix["battery"].native_value == 88   # rounded int
    assert by_suffix["qcn_d1"].native_value == "Good"


def test_moisture_unknown_when_all_training():
    coord = _coord(_reading(all_training=True))
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    by_suffix = {s._suffix: s for s in sensors}
    assert by_suffix["moisture"].native_value is None       # omitted when all-training
    assert by_suffix["battery"].native_value == 88          # telemetry still reported


def test_unavailable_when_stale_beyond_skip():
    coord = _coord(_reading())
    coord.reading.return_value = _reading()
    coord.reading.return_value = DeviceReading(**{**_reading().__dict__, "sync_delay_hours": 99.0})
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False


def test_unavailable_when_feed_is_stale_even_if_reading_is_fresh():
    # FIX 8 "both signals": expire_after_minutes (default 45) must also gate
    # availability -- a quiet feed (no successful coordinator update recently)
    # makes sensors unavailable even though the last reading itself is fresh.
    stale_success = dt_util.utcnow() - timedelta(hours=2)
    coord = _coord(_reading(), last_success_time=stale_success)
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False


def test_unavailable_when_never_successfully_updated():
    coord = _coord(_reading())
    coord.last_success_time = None   # no successful update has ever landed
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False

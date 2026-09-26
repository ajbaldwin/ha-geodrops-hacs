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


def _coord(reading, skip_hours=12, seen=None):
    c = MagicMock()
    c.reading.return_value = reading
    c.entry.options = {const.CONF_SKIP_HOURS: skip_hours}
    # default: the device's row just arrived, so tests that don't care about
    # FIX 8's expire_after_minutes wiring stay within the window
    c.reading_time.return_value = seen if seen is not None else dt_util.utcnow()
    return c


def test_16_sensors_per_device():
    assert len(SENSOR_SPECS) == 16


def test_moisture_value_and_state():
    coord = _coord(_reading())
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    by_suffix = {s._suffix: s for s in sensors}
    assert by_suffix["moisture"].native_value == 42.5
    assert by_suffix["moisture_state"].native_value == "moist_plus"
    assert by_suffix["battery"].native_value == 88   # rounded int
    assert by_suffix["qcn_d1"].native_value == "good"


def test_moisture_unknown_when_all_training():
    coord = _coord(_reading(all_training=True))
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    by_suffix = {s._suffix: s for s in sensors}
    assert by_suffix["moisture"].native_value is None       # omitted when all-training
    assert by_suffix["battery"].native_value == 88          # telemetry still reported


def test_unavailable_when_stale_beyond_skip():
    coord = _coord(_reading())
    coord.reading.return_value = DeviceReading(**{**_reading().__dict__, "sync_delay_hours": 99.0})
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False


def test_unavailable_when_feed_is_stale_even_if_reading_is_fresh():
    # FIX 8 "both signals": expire_after_minutes (default 80) must also gate
    # availability -- a device whose row has not come back from any poll recently
    # (failed polls, or polls that return no row for it) goes unavailable even
    # though the last reading's own sync delay is fresh.
    coord = _coord(_reading(), seen=dt_util.utcnow() - timedelta(hours=2))
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False


def test_default_expire_rides_out_three_missed_polls():
    # default 80 min at the default 20 min poll: 3 consecutive polls without the
    # device's row (failed or empty) keep sensors up; the 4th makes them unavailable
    assert const.DEFAULT_EXPIRE_MINUTES == 80
    device = {"serial": "AAA111", "device_id": 1001, "name": "Front"}
    recent = _coord(_reading(), seen=dt_util.utcnow() - timedelta(minutes=75))
    assert build_sensors(recent, device)[0].available is True
    old = _coord(_reading(), seen=dt_util.utcnow() - timedelta(minutes=85))
    assert build_sensors(old, device)[0].available is False


def test_unavailable_when_never_successfully_updated():
    coord = _coord(_reading())
    coord.reading_time.return_value = None   # no poll has ever returned this device
    sensors = build_sensors(coord, {"serial": "AAA111", "device_id": 1001, "name": "Front"})
    assert sensors[0].available is False


async def test_device_info_area_and_model(hass):
    from homeassistant.helpers import area_registry as ar
    area = ar.async_get(hass).async_create("Backyard")
    coord = _coord(_reading())
    coord.hass = hass
    device = {"serial": "AAA111", "device_id": 1001, "name": "Front", "area_id": area.id}
    sensors = build_sensors(coord, device)
    info = sensors[0].device_info
    assert info["suggested_area"] == "Backyard"
    assert info["model"] == "GeoDrops Droplet"
    assert info["name"] == "Front"
    assert info["serial_number"] == "AAA111"
    assert "sw_version" not in info   # was hard-coded; GeoDrops doesn't report firmware


DEVICE = {"serial": "AAA111", "device_id": 1001, "name": "Front"}


def _sensor(coord, suffix):
    return {s._suffix: s for s in build_sensors(coord, DEVICE)}[suffix]


def _with(**changes):
    return DeviceReading(**{**_reading().__dict__, **changes})


def test_missing_values_read_unknown_not_zero():
    coord = _coord(_with(battery_pct=None, temp_d1=None, moisture_pct=None))
    assert _sensor(coord, "battery").native_value is None
    assert _sensor(coord, "temp_d1").native_value is None
    assert _sensor(coord, "moisture").native_value is None


def test_unknown_sync_delay_does_not_make_the_probe_unavailable():
    coord = _coord(_with(sync_delay_hours=None))
    assert _sensor(coord, "moisture").available is True


def test_unavailable_when_reading_timestamp_is_older_than_skip():
    # the row's sync delay is frozen at 2 h, but the reading itself is 13 h old
    old = dt_util.utcnow() - timedelta(hours=13)
    coord = _coord(_with(read_at=old), skip_hours=12)
    assert _sensor(coord, "moisture").available is False


def test_available_when_reading_timestamp_is_recent():
    recent = dt_util.utcnow() - timedelta(hours=3)
    coord = _coord(_with(read_at=recent), skip_hours=12)
    assert _sensor(coord, "moisture").available is True


def test_last_reading_sensor_reports_the_reading_timestamp():
    from homeassistant.components.sensor import SensorDeviceClass
    when = dt_util.utcnow() - timedelta(minutes=30)
    sensor = _sensor(_coord(_with(read_at=when)), "last_reading")
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.native_value == when
    assert sensor.unique_id == "AAA111_last_reading"


def test_last_reading_is_reported_even_while_training():
    when = dt_util.utcnow()
    sensor = _sensor(_coord(DeviceReading(**{**_reading(all_training=True).__dict__,
                                             "read_at": when})), "last_reading")
    assert sensor.native_value == when


def test_no_reading_yet_is_unavailable_and_unknown():
    coord = _coord(None)
    sensor = _sensor(coord, "moisture_state")
    assert sensor.available is False
    assert sensor.native_value is None


def test_depth_sensors_share_a_translation_with_a_depth_placeholder():
    coord = _coord(_reading())
    sensor = _sensor(coord, "qcn_d2")
    assert sensor.translation_key == "qcn_depth"
    assert sensor.translation_placeholders == {"depth": "2"}
    assert sensor.unique_id == "AAA111_qcn_d2"   # unchanged, so entities carry over

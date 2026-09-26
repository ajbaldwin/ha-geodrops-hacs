from datetime import date, datetime, timedelta, timezone

from custom_components.geodrops import transform as t


class Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_qcn_and_moisture_state_maps():
    # states are translation keys; the UI shows "Good", "Wet+", ...
    assert t.qcn_to_state(2) == "good"
    assert t.qcn_to_state(-1) == "training"
    assert t.qcn_to_state(99) is None           # HA's own "unknown"
    assert t.moisture_index_to_state(0) == "dry"
    assert t.moisture_index_to_state(5) == "wet_plus"
    assert t.moisture_index_to_state(-1) is None
    assert t.moisture_index_to_state(99) is None


def test_classify_staleness_strict_gt():
    assert t.classify_staleness(5, 6, 12) == "ok"
    assert t.classify_staleness(6, 6, 12) == "ok"      # strict >
    assert t.classify_staleness(7, 6, 12) == "warn"
    assert t.classify_staleness(13, 6, 12) == "skip"


def test_reading_from_row_defaults_and_all_training():
    row = Row(deviceId=1001, moistureIndex=None, qcnDepth1=None,
              qcnDepth2=None, qcnDepth3=None)
    reading = t.reading_from_row(row)
    assert reading.device_id == 1001
    assert reading.moisture_index == -1     # _qcn default
    assert reading.moisture_pct is None     # missing stays unknown, not a fake 0
    assert t.all_training(reading) is True


def test_not_all_training_when_one_depth_known():
    row = Row(deviceId=1002, qcnDepth1=2, qcnDepth2=None, qcnDepth3=None)
    reading = t.reading_from_row(row)
    assert t.all_training(reading) is False


def test_missing_numbers_stay_none_but_zero_is_kept():
    # A NULL temperature/battery must read "unknown", not 0 °C / 0 % (which
    # fires frost and low-battery automations); a real 0 is still a value
    row = Row(deviceId=1001, temperatureCDepth1=None, miscBattPercent=0.0)
    reading = t.reading_from_row(row)
    assert reading.temp_d1 is None
    assert reading.temp_surface is None     # column absent entirely
    assert reading.battery_pct == 0.0


def test_read_at_comes_from_the_date_timestamp():
    when = datetime(2026, 9, 26, 8, 30, tzinfo=timezone.utc)
    assert t.reading_from_row(Row(deviceId=1, date=when)).read_at == when


def test_naive_date_is_treated_as_utc():
    naive = datetime(2026, 9, 26, 8, 30)
    assert t.reading_from_row(Row(deviceId=1, date=naive)).read_at == naive.replace(
        tzinfo=timezone.utc)


def test_non_timestamp_date_is_unknown():
    assert t.reading_from_row(Row(deviceId=1, date=date(2026, 9, 26))).read_at is None
    assert t.reading_from_row(Row(deviceId=1)).read_at is None


def _aged(sync_delay, read_hours_ago, now):
    row = Row(deviceId=1, miscSensorSyncDelayHour=sync_delay,
              date=None if read_hours_ago is None else now - timedelta(hours=read_hours_ago))
    return t.reading_from_row(row)


def test_data_age_grows_with_the_clock_when_the_row_is_frozen():
    # GeoDrops can keep serving the same row (sync delay frozen at 1 h) while
    # the probe has gone quiet; the reading's own timestamp still ages
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert t.data_age_hours(_aged(1.0, 20, now), now) == 20


def test_data_age_uses_sync_delay_when_it_is_larger():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert t.data_age_hours(_aged(15.0, 2, now), now) == 15.0


def test_data_age_falls_back_to_whatever_is_known():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert t.data_age_hours(_aged(3.0, None, now), now) == 3.0
    assert t.data_age_hours(_aged(None, 4, now), now) == 4
    assert t.data_age_hours(_aged(None, None, now), now) is None

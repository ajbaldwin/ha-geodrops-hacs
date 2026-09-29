from datetime import UTC, datetime, timedelta

from aiogeodrops import DeviceReading

from custom_components.geodrops import transform as t


def _reading(**changes):
    base = {
        "device_id": 1,
        "sync_delay_hours": None,
        "moisture_index": -1,
        "moisture_pct": None,
        "moisture_d1": None,
        "moisture_d2": None,
        "moisture_d3": None,
        "temp_surface": None,
        "temp_d1": None,
        "temp_d2": None,
        "temp_d3": None,
        "battery_pct": None,
        "sun_7d": None,
        "qcn_d1": -1,
        "qcn_d2": -1,
        "qcn_d3": -1,
    }
    return DeviceReading(**{**base, **changes})


def test_qcn_and_moisture_state_maps():
    # states are translation keys; the UI shows "Good", "Wet+", ...
    assert t.qcn_to_state(2) == "good"
    assert t.qcn_to_state(-1) == "training"
    assert t.qcn_to_state(99) is None  # HA's own "unknown"
    assert t.moisture_index_to_state(0) == "dry"
    assert t.moisture_index_to_state(5) == "wet_plus"
    assert t.moisture_index_to_state(-1) is None
    assert t.moisture_index_to_state(99) is None


def test_classify_staleness_strict_gt():
    assert t.classify_staleness(5, 6, 12) == "ok"
    assert t.classify_staleness(6, 6, 12) == "ok"  # strict >
    assert t.classify_staleness(7, 6, 12) == "warn"
    assert t.classify_staleness(13, 6, 12) == "skip"


def _aged(sync_delay, read_hours_ago, now):
    return _reading(
        sync_delay_hours=sync_delay,
        read_at=None
        if read_hours_ago is None
        else now - timedelta(hours=read_hours_ago),
    )


def test_data_age_grows_with_the_clock_when_the_row_is_frozen():
    # GeoDrops can keep serving the same row (sync delay frozen at 1 h) while
    # the probe has gone quiet; the reading's own timestamp still ages
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert t.data_age_hours(_aged(1.0, 20, now), now) == 20


def test_data_age_uses_sync_delay_when_it_is_larger():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert t.data_age_hours(_aged(15.0, 2, now), now) == 15.0


def test_data_age_falls_back_to_whatever_is_known():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert t.data_age_hours(_aged(3.0, None, now), now) == 3.0
    assert t.data_age_hours(_aged(None, 4, now), now) == 4
    assert t.data_age_hours(_aged(None, None, now), now) is None

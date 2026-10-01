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


def test_status_takes_the_most_urgent_code():
    s = t.next_action_to_status
    assert s(frozenset()) == "ok"
    assert s(frozenset({"DW_M_LOW12", "LAX_M_EVA3", "SOMETHING_NEW"})) == "ok"
    assert s(frozenset({"MEM_T_LRN"})) == "calibrating"
    assert s(frozenset({"ATT_SS_NEW"})) == "calibrating"
    assert s(frozenset({"ATT_DW_NEW", "ATT_SS_NEW"})) == "max_moisture_required"
    assert s(frozenset({"DW_RENEW", "ATT_DW_NEW"})) == "wick_renewal_needed"
    assert s(frozenset({"CHK_T_HWR", "DW_RENEW"})) == "hardware_check"
    assert s(frozenset({"ERR_NULL", "CHK_T_HWR"})) == "error"
    assert s(None) is None  # no nextAction column
    assert set(t.STATUS_OPTIONS) == {
        "ok", "calibrating", "max_moisture_required", "wick_renewal_needed",
        "hardware_check", "error",
    }  # fmt: skip


def test_has_code():
    assert t.has_code(frozenset({"DW_RENEW"}), t.WICK_CODES) is True
    assert t.has_code(frozenset(), t.WICK_CODES) is False
    assert t.has_code(None, t.WICK_CODES) is None


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
    assert t.data_age_hours(_aged(4.0, 2, now), now) == 4.0


def test_data_age_ignores_an_impossible_sync_delay():
    # GeoDrops served ~2053 h on rows an hour old (2026-09-30); the probe was
    # reporting every 30 minutes, so its age is the reading's own age
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert t.data_age_hours(_aged(2053.1, 1, now), now) == 1


def test_sync_delay_is_none_beyond_the_slack():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    slack = t.SYNC_DELAY_SLACK_HOURS
    assert t.sync_delay_hours(_aged(1.0 + slack, 1, now), now) == 1.0 + slack
    assert t.sync_delay_hours(_aged(1.1 + slack, 1, now), now) is None
    # a row stamped slightly in the future (end of its interval) still passes
    assert t.sync_delay_hours(_aged(1.2, -0.25, now), now) == 1.2
    # without a timestamp there is nothing to check against
    assert t.sync_delay_hours(_aged(2053.1, None, now), now) == 2053.1


def test_data_age_falls_back_to_whatever_is_known():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert t.data_age_hours(_aged(3.0, None, now), now) == 3.0
    assert t.data_age_hours(_aged(None, 4, now), now) == 4
    assert t.data_age_hours(_aged(None, None, now), now) is None

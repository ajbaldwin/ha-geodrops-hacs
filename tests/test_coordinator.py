import pytest
from unittest.mock import MagicMock
from custom_components.geodrops.bigquery_api import QueryError
from custom_components.geodrops.coordinator import GeoDropsCoordinator
from custom_components.geodrops.transform import DeviceReading
from custom_components.geodrops import const


def _reading(device_id, pct):
    return DeviceReading(device_id=device_id, sync_delay_hours=1.0, moisture_index=2,
                         moisture_pct=pct, moisture_d1=pct, moisture_d2=pct, moisture_d3=pct,
                         temp_surface=20.0, temp_d1=20.0, temp_d2=20.0, temp_d3=20.0,
                         battery_pct=90.0, sun_7d=5.0, qcn_d1=2, qcn_d2=2, qcn_d3=2)


async def test_coordinator_fetches_and_maps(hass, monkeypatch):
    entry = MagicMock()
    entry.options = {const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}],
                     const.CONF_SCAN_INTERVAL: 20, const.CONF_LOOKBACK_HOURS: 12}
    client = MagicMock()
    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest",
                        lambda c, ids, lb: {1001: _reading(1001, 42.0)})
    coord = GeoDropsCoordinator(hass, entry, client)
    assert coord.reading_time(1001) is None
    data = await coord._async_update_data()
    assert data[1001].moisture_pct == 42.0
    assert coord.device_ids == [1001]
    assert coord.reading_time(1001) is not None   # FIX 8: a returned row stamps the time


async def test_coordinator_does_not_stamp_success_on_failure(hass, monkeypatch):
    entry = MagicMock()
    entry.options = {const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}],
                     const.CONF_SCAN_INTERVAL: 20, const.CONF_LOOKBACK_HOURS: 12}
    client = MagicMock()

    def _raise(c, ids, lb):
        raise QueryError("boom")

    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest", _raise)
    coord = GeoDropsCoordinator(hass, entry, client)
    with pytest.raises(Exception):   # UpdateFailed
        await coord._async_update_data()
    assert coord.reading_time(1001) is None


async def test_coordinator_raises_auth_failed_when_key_rejected(hass, monkeypatch):
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from custom_components.geodrops.bigquery_api import AuthError

    entry = MagicMock()
    entry.options = {const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}]}

    def _raise(c, ids, lb):
        raise AuthError("invalid_grant")

    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest", _raise)
    coord = GeoDropsCoordinator(hass, entry, MagicMock())
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
    assert coord.reading_time(1001) is None


def _two_device_entry():
    entry = MagicMock()
    entry.options = {const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"},
                                          {"serial": "BBB222", "device_id": 1002, "name": "Back"}]}
    return entry


async def test_poll_without_a_device_row_keeps_its_last_reading(hass, monkeypatch):
    # GeoDrops' table briefly holds no recent rows twice a day: the query succeeds
    # but returns nothing. That must not wipe the readings the last poll had.
    polls = iter([{1001: _reading(1001, 42.0), 1002: _reading(1002, 30.0)},
                  {1002: _reading(1002, 31.0)}])
    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest",
                        lambda c, ids, lb: next(polls))
    coord = GeoDropsCoordinator(hass, _two_device_entry(), MagicMock())
    coord.data = await coord._async_update_data()
    first_seen = coord.reading_time(1001)
    coord.data = await coord._async_update_data()
    assert coord.reading(1001).moisture_pct == 42.0
    assert coord.reading(1002).moisture_pct == 31.0
    assert coord.reading_time(1001) == first_seen      # not refreshed by the empty poll
    assert coord.reading_time(1002) > first_seen


async def test_reading_time_is_none_until_a_row_arrives(hass, monkeypatch):
    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest",
                        lambda c, ids, lb: {1001: _reading(1001, 42.0)})
    coord = GeoDropsCoordinator(hass, _two_device_entry(), MagicMock())
    coord.data = await coord._async_update_data()
    assert coord.reading_time(1001) is not None
    assert coord.reading_time(1002) is None
    assert coord.reading(1002) is None


async def test_removed_device_is_dropped(hass, monkeypatch):
    monkeypatch.setattr("custom_components.geodrops.coordinator.fetch_latest",
                        lambda c, ids, lb: {i: _reading(i, 40.0) for i in ids})
    entry = _two_device_entry()
    coord = GeoDropsCoordinator(hass, entry, MagicMock())
    coord.data = await coord._async_update_data()
    entry.options = {const.CONF_DEVICES: [{"serial": "BBB222", "device_id": 1002, "name": "Back"}]}
    coord.data = await coord._async_update_data()
    assert coord.reading(1001) is None
    assert coord.reading_time(1001) is None

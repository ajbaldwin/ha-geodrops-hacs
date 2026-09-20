import pytest
from unittest.mock import MagicMock
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
    data = await coord._async_update_data()
    assert data[1001].moisture_pct == 42.0
    assert coord.device_ids == [1001]

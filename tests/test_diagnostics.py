from datetime import datetime, timezone

from aiogeodrops import DeviceReading, GeoDropsQueryError
from custom_components.geodrops import const
from custom_components.geodrops.diagnostics import async_get_config_entry_diagnostics
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.common import patch_client

READ_AT = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)


def _reading():
    return DeviceReading(device_id=1001, sync_delay_hours=1.0, moisture_index=2,
                         moisture_pct=42.0, moisture_d1=42.0, moisture_d2=42.0, moisture_d3=42.0,
                         temp_surface=20.0, temp_d1=20.0, temp_d2=20.0, temp_d3=20.0,
                         battery_pct=90.0, sun_7d=5.0, qcn_d1=2, qcn_d2=2, qcn_d3=2,
                         read_at=READ_AT)


async def _setup(hass):
    entry = MockConfigEntry(
        domain=const.DOMAIN, unique_id="my-project",
        data={const.CONF_PROJECT_ID: "my-project",
              const.CONF_CREDENTIALS_JSON: '{"private_key":"secret"}'},
        options={const.CONF_DEVICES: [
            {"serial": "AAA111", "device_id": 1001, "name": "Front"},
            {"serial": "BBB222", "device_id": 1002, "name": "Back"}]},
    )
    entry.add_to_hass(hass)
    with patch_client("fetch_latest", return_value={1001: _reading()}):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_diagnostics_redact_the_key_and_project(hass):
    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"] == {const.CONF_PROJECT_ID: "**REDACTED**",
                                     const.CONF_CREDENTIALS_JSON: "**REDACTED**"}
    assert "secret" not in str(diag)
    assert "my-project" not in str(diag)
    assert diag["entry"]["options"] == dict(entry.options)
    assert diag["coordinator"] == {"last_update_success": True, "last_exception": None,
                                   "update_interval_seconds": 1200.0}


async def test_diagnostics_show_each_probes_last_reading(hass):
    entry = await _setup(hass)
    probes = (await async_get_config_entry_diagnostics(hass, entry))["probes"]

    front = probes["AAA111"]
    assert front["device_id"] == 1001
    assert front["last_seen_in_poll"] is not None
    assert front["reading"]["moisture_pct"] == 42.0
    assert front["reading"]["read_at"] == READ_AT
    # a probe the poll hasn't returned yet
    assert probes["BBB222"] == {"device_id": 1002, "last_seen_in_poll": None, "reading": None}


async def test_diagnostics_redact_the_project_from_the_last_error(hass):
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    with patch_client("fetch_latest",
                      side_effect=GeoDropsQueryError("404 Not found: Job my-project:US.job_1")):
        await coordinator.async_refresh()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["coordinator"]["last_update_success"] is False
    assert diag["coordinator"]["last_exception"].startswith("UpdateFailed: ")
    assert "Job **REDACTED**:US.job_1" in diag["coordinator"]["last_exception"]
    assert "my-project" not in str(diag)

from unittest.mock import patch, MagicMock
from homeassistant.config_entries import ConfigEntryState, SOURCE_REAUTH
from homeassistant.helpers import entity_registry as er
from custom_components.geodrops import const
from custom_components.geodrops.bigquery_api import AuthError, CredentialsError, QueryError
from custom_components.geodrops.transform import DeviceReading
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _reading(device_id=1001):
    return DeviceReading(device_id=device_id, sync_delay_hours=1.0, moisture_index=2,
                         moisture_pct=42.0, moisture_d1=42.0, moisture_d2=42.0, moisture_d3=42.0,
                         temp_surface=20.0, temp_d1=20.0, temp_d2=20.0, temp_d3=20.0,
                         battery_pct=90.0, sun_7d=5.0, qcn_d1=2, qcn_d2=2, qcn_d3=2)


def _entry(hass):
    entry = MockConfigEntry(
        domain=const.DOMAIN, unique_id="p",
        data={const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'},
        options={const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}]},
    )
    entry.add_to_hass(hass)
    return entry


def _patch_client(**kw):
    return patch("custom_components.geodrops.make_client", return_value=MagicMock(), **kw)


def _patch_fetch(**kw):
    kw.setdefault("return_value", {1001: _reading()})
    return patch("custom_components.geodrops.coordinator.fetch_latest", **kw)


def _reauth_flows(hass):
    return [f for f in hass.config_entries.flow.async_progress_by_handler(const.DOMAIN)
            if f["context"]["source"] == SOURCE_REAUTH]


async def test_setup_creates_16_sensors_then_unloads(hass):
    entry = _entry(hass)
    with _patch_client() as make_client, _patch_fetch():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 16
    assert hass.states.get("sensor.front_dominant_moisture").state == "42.0"
    client = make_client.return_value
    client.close.assert_not_called()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    client.close.assert_called_once()   # every reload used to leak an HTTP session


async def test_entity_ids_names_and_states(hass):
    # translated names must produce the same entity ids as the old hard-coded ones
    entry = _entry(hass)
    with _patch_client(), _patch_fetch():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    entity_ids = {e.entity_id for e in
                  er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert entity_ids == {f"sensor.front_{s}" for s in (
        "dominant_moisture", "moisture_state", "moisture_depth_1", "moisture_depth_2",
        "moisture_depth_3", "quality_depth_1", "quality_depth_2", "quality_depth_3",
        "battery", "sync_delay", "surface_temperature", "temperature_depth_1",
        "temperature_depth_2", "temperature_depth_3", "avg_7_day_sun", "last_reading")}
    quality = hass.states.get("sensor.front_quality_depth_2")
    assert quality.attributes["friendly_name"] == "Front Quality Depth 2"
    assert quality.state == "good"
    assert quality.attributes["options"] == ["bad", "poor", "good", "training"]
    assert hass.states.get("sensor.front_moisture_state").state == "moist"
    assert hass.states.get("sensor.front_avg_7_day_sun").attributes["friendly_name"] ==         "Front Avg. 7-Day Sun"


async def test_failed_first_refresh_closes_the_client(hass):
    # SETUP_RETRY re-runs setup with a fresh client; the failed one must not leak
    entry = _entry(hass)
    with _patch_client() as make_client, _patch_fetch(side_effect=QueryError("503")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    make_client.return_value.close.assert_called_once()


async def test_options_change_reloads_entry_once(hass):
    entry = _entry(hass)
    with _patch_client() as make_client, _patch_fetch():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert make_client.call_count == 1
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "settings"})
        await hass.config_entries.options.async_configure(
            result["flow_id"], {const.CONF_SCAN_INTERVAL: 30, const.CONF_LOOKBACK_HOURS: 12,
                                const.CONF_WARN_HOURS: 6, const.CONF_SKIP_HOURS: 12,
                                const.CONF_EXPIRE_MINUTES: 80})
        await hass.async_block_till_done()
    assert make_client.call_count == 2   # reloaded exactly once
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval.total_seconds() == 30 * 60


async def test_reauth_reloads_entry_once(hass):
    # the update listener used to reload on the key change too: two reloads,
    # two BigQuery queries
    entry = _entry(hass)
    with _patch_client() as make_client, _patch_fetch() as fetch:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await entry.start_reauth_flow(hass)
        with patch("custom_components.geodrops.config_flow.make_client",
                   return_value=MagicMock()),              patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"new"}'})
        await hass.async_block_till_done()
    assert make_client.call_count == 2
    assert fetch.call_count == 2
    assert entry.state is ConfigEntryState.LOADED


async def test_unparseable_stored_key_starts_reauth(hass):
    entry = _entry(hass)
    with _patch_client(side_effect=CredentialsError("bad json")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_rejected_key_on_first_refresh_starts_reauth(hass):
    entry = _entry(hass)
    with _patch_client(), _patch_fetch(side_effect=AuthError("invalid_grant")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_query_error_on_first_refresh_retries_without_reauth(hass):
    entry = _entry(hass)
    with _patch_client(), _patch_fetch(side_effect=QueryError("403 access denied")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert _reauth_flows(hass) == []


async def test_key_rejected_after_setup_starts_reauth(hass):
    entry = _entry(hass)
    with _patch_client(), _patch_fetch():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = entry.runtime_data
    with _patch_fetch(side_effect=AuthError("invalid_grant")):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert len(_reauth_flows(hass)) == 1

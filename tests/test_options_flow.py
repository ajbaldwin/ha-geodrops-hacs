import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from unittest.mock import patch, MagicMock
from homeassistant.helpers import device_registry as dr
from custom_components.geodrops import const
from custom_components.geodrops.bigquery_api import AuthError, CredentialsError, QueryError
from custom_components.geodrops.transform import DeviceReading
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _reading(device_id=1002):
    return DeviceReading(device_id=device_id, sync_delay_hours=1.0, moisture_index=2,
                         moisture_pct=30.0, moisture_d1=30.0, moisture_d2=30.0, moisture_d3=30.0,
                         temp_surface=20.0, temp_d1=20.0, temp_d2=20.0, temp_d3=20.0,
                         battery_pct=80.0, sun_7d=5.0, qcn_d1=2, qcn_d2=2, qcn_d3=2)


def _entry():
    return MockConfigEntry(
        domain=const.DOMAIN,
        data={const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'},
        options={const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}]},
    )


async def test_settings_updates_interval(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {const.CONF_SCAN_INTERVAL: 30, const.CONF_LOOKBACK_HOURS: 12,
                            const.CONF_WARN_HOURS: 6, const.CONF_SKIP_HOURS: 12,
                            const.CONF_EXPIRE_MINUTES: 45})
    assert entry.options[const.CONF_SCAN_INTERVAL] == 30
    assert len(entry.options[const.CONF_DEVICES]) == 1   # devices preserved


async def test_add_second_device(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_device"})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "aaa222", const.DEV_NAME: "Back"})
    serials = [d[const.DEV_SERIAL] for d in entry.options[const.CONF_DEVICES]]
    assert serials == ["AAA111", "AAA222"]


async def test_remove_device(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(const.DOMAIN, "AAA111")})

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_device"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"device": "AAA111"})
    assert entry.options[const.CONF_DEVICES] == []
    # the device (and its 15 entities) must be purged from the registry, not orphaned
    assert registry.async_get_device(identifiers={(const.DOMAIN, "AAA111")}) is None
    assert registry.async_get(device.id) is None


_GOOD_SETTINGS = {const.CONF_SCAN_INTERVAL: 20, const.CONF_LOOKBACK_HOURS: 12,
                  const.CONF_WARN_HOURS: 6, const.CONF_SKIP_HOURS: 12,
                  const.CONF_EXPIRE_MINUTES: 80}


async def _open(hass, step, options=None):
    entry = _entry()
    if options is not None:
        entry = MockConfigEntry(domain=const.DOMAIN, data=entry.data, options=options)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step})
    return entry, result


@pytest.mark.parametrize(("key", "value"), [
    (const.CONF_SCAN_INTERVAL, 0),      # would query BigQuery back-to-back
    (const.CONF_SCAN_INTERVAL, 4),
    (const.CONF_LOOKBACK_HOURS, -5),
    (const.CONF_LOOKBACK_HOURS, 0),
    (const.CONF_WARN_HOURS, 0),
    (const.CONF_SKIP_HOURS, 0),
    (const.CONF_EXPIRE_MINUTES, 0),
])
async def test_settings_reject_out_of_range_values(hass, key, value):
    entry, result = await _open(hass, "settings")
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**_GOOD_SETTINGS, key: value})
    assert key not in entry.options


async def test_settings_reject_warn_above_skip(hass):
    entry, result = await _open(hass, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_GOOD_SETTINGS, const.CONF_WARN_HOURS: 13})
    assert result["errors"] == {const.CONF_WARN_HOURS: "warn_above_skip"}
    assert const.CONF_WARN_HOURS not in entry.options


async def test_settings_reject_expire_not_longer_than_poll(hass):
    # sensors would go unavailable between every pair of polls
    entry, result = await _open(hass, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_GOOD_SETTINGS, const.CONF_SCAN_INTERVAL: 30,
                            const.CONF_EXPIRE_MINUTES: 30})
    assert result["errors"] == {const.CONF_EXPIRE_MINUTES: "expire_below_interval"}
    assert const.CONF_EXPIRE_MINUTES not in entry.options


async def test_settings_rejected_form_keeps_what_was_typed(hass):
    _, result = await _open(hass, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_GOOD_SETTINGS, const.CONF_WARN_HOURS: 13})
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults[const.CONF_WARN_HOURS] == 13


async def test_add_duplicate_serial_is_rejected_without_a_query(hass):
    _, result = await _open(hass, "add_device")
    with patch("custom_components.geodrops.config_flow.make_client") as make_client:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {const.DEV_SERIAL: " aaa111", const.DEV_NAME: "Again"})
    assert result["errors"] == {"base": "duplicate_device"}
    make_client.assert_not_called()


@pytest.mark.parametrize(("patches", "error"), [
    ({"lookup_serial": {"return_value": None}}, "device_not_found"),
    ({"lookup_serial": {"side_effect": QueryError("503")}}, "cannot_connect"),
    ({"lookup_serial": {"side_effect": AuthError("invalid_grant")}}, "invalid_auth"),
    ({"make_client": {"side_effect": CredentialsError("bad")}}, "invalid_credentials"),
])
async def test_add_device_errors(hass, patches, error):
    entry, result = await _open(hass, "add_device")
    kw = {"make_client": {"return_value": MagicMock()},
          "lookup_serial": {"return_value": _reading()}, **patches}
    with patch("custom_components.geodrops.config_flow.make_client", **kw["make_client"]), \
         patch("custom_components.geodrops.config_flow.lookup_serial", **kw["lookup_serial"]):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "BBB222", const.DEV_NAME: "Back"})
    assert result["step_id"] == "add_device"
    assert result["errors"] == {"base": error}
    assert len(entry.options[const.CONF_DEVICES]) == 1


async def test_add_device_saves_id_and_area_and_closes_client(hass):
    entry, result = await _open(hass, "add_device")
    client = MagicMock()
    with patch("custom_components.geodrops.config_flow.make_client", return_value=client), \
         patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {const.DEV_SERIAL: "BBB222", const.DEV_NAME: "Back", const.DEV_AREA: "garden"})
    assert entry.options[const.CONF_DEVICES][1] == {
        "serial": "BBB222", "device_id": 1002, "name": "Back", "area_id": "garden"}
    client.close.assert_called_once()


async def test_remove_with_no_probes_aborts(hass):
    _, result = await _open(hass, "remove_device", options={const.CONF_DEVICES: []})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_devices"

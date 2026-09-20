import pytest
from unittest.mock import patch, MagicMock
from homeassistant.helpers import device_registry as dr
from custom_components.geodrops import const
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

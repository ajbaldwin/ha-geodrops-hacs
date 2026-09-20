import pytest
from unittest.mock import patch, MagicMock
from homeassistant import config_entries, data_entry_flow
from custom_components.geodrops import const
from custom_components.geodrops.transform import DeviceReading

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


def _reading(device_id=1001):
    return DeviceReading(device_id=device_id, sync_delay_hours=1.0, moisture_index=2,
                         moisture_pct=42.0, moisture_d1=42.0, moisture_d2=42.0, moisture_d3=42.0,
                         temp_surface=20.0, temp_d1=20.0, temp_d2=20.0, temp_d3=20.0,
                         battery_pct=90.0, sun_7d=5.0, qcn_d1=2, qcn_d2=2, qcn_d3=2)


async def test_full_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"

    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.fetch_latest", return_value={}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "your-gcp-project-id",
             const.CONF_CREDENTIALS_JSON: '{"type":"service_account"}'})
    assert result["step_id"] == "add_device"

    with patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "aaa111 ", const.DEV_NAME: "Front"})
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    devices = result["options"][const.CONF_DEVICES]
    assert devices[0][const.DEV_SERIAL] == "AAA111"   # normalized
    assert devices[0][const.DEV_ID] == 1001


async def test_bad_credentials_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client",
               side_effect=__import__("custom_components.geodrops.bigquery_api",
                                      fromlist=["CredentialsError"]).CredentialsError("bad")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: "not json"})
    assert result["errors"] == {"base": "invalid_credentials"}


async def test_unknown_serial_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.fetch_latest", return_value={}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'})
    with patch("custom_components.geodrops.config_flow.lookup_serial", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "ZZZ999", const.DEV_NAME: "Nope"})
    assert result["errors"] == {"base": "device_not_found"}

import pytest
from unittest.mock import patch, MagicMock
from homeassistant import config_entries, data_entry_flow
from custom_components.geodrops import const
from custom_components.geodrops.bigquery_api import AuthError, QueryError
from custom_components.geodrops.transform import DeviceReading
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "your-gcp-project-id",
             const.CONF_CREDENTIALS_JSON: '{"type":"service_account"}'})
    assert result["step_id"] == "add_device"

    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()),          patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()):
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
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()),          patch("custom_components.geodrops.config_flow.lookup_serial", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "ZZZ999", const.DEV_NAME: "Nope"})
    assert result["errors"] == {"base": "device_not_found"}


def _existing_entry(hass, project="p", key='{"type":"old"}'):
    entry = MockConfigEntry(
        domain=const.DOMAIN, unique_id=project,
        data={const.CONF_PROJECT_ID: project, const.CONF_CREDENTIALS_JSON: key},
        options={const.CONF_DEVICES: [{"serial": "AAA111", "device_id": 1001, "name": "Front"}]},
    )
    entry.add_to_hass(hass)
    return entry


async def test_rejected_key_in_user_step_shows_invalid_auth(hass):
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access",
               side_effect=AuthError("invalid_grant")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_replaces_key_and_keeps_probes(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["project_id"] == "p"

    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"new"}'})
    await hass.async_block_till_done()   # let the triggered reload finish
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"new"}'
    assert entry.data[const.CONF_PROJECT_ID] == "p"
    assert len(entry.options[const.CONF_DEVICES]) == 1


async def test_reauth_with_another_rejected_key_shows_error(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reauth_flow(hass)
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access",
               side_effect=AuthError("invalid_grant")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"also-dead"}'})
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"old"}'   # untouched


async def test_reconfigure_blank_key_keeps_stored_key(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    with patch("custom_components.geodrops.config_flow.make_client",
               return_value=MagicMock()) as make_client, \
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROJECT_ID: "new-project"})
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    make_client.assert_called_once_with("new-project", '{"type":"old"}')
    assert entry.data == {const.CONF_PROJECT_ID: "new-project",
                          const.CONF_CREDENTIALS_JSON: '{"type":"old"}'}
    assert entry.unique_id == "new-project"
    assert len(entry.options[const.CONF_DEVICES]) == 1


async def test_reconfigure_rotates_key(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: '{"type":"new"}'})
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"new"}'
    assert entry.unique_id == "p"


async def test_reconfigure_to_already_configured_project_aborts(hass):
    entry = _existing_entry(hass, project="p")
    _existing_entry(hass, project="other")
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROJECT_ID: "other"})
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[const.CONF_PROJECT_ID] == "p"


async def test_reconfigure_bad_project_shows_error(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access",
               side_effect=QueryError("404 project not found")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROJECT_ID: "typo-project"})
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[const.CONF_PROJECT_ID] == "p"


async def _at_add_device(hass, project="p"):
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.validate_access", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: project, const.CONF_CREDENTIALS_JSON: '{"type":"x"}'})
    assert result["step_id"] == "add_device"
    return result


async def test_already_configured_project_aborts_before_asking_for_a_probe(hass):
    _existing_entry(hass, project="p")
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client") as make_client:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.CONF_PROJECT_ID: " p ", const.CONF_CREDENTIALS_JSON: '{"type":"x"}'})
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    make_client.assert_not_called()


async def test_project_id_is_stripped(hass):
    result = await _at_add_device(hass, project="  my-project \n")
    with patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()), \
         patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "AAA111", const.DEV_NAME: "Front"})
    assert result["data"][const.CONF_PROJECT_ID] == "my-project"
    assert result["result"].unique_id == "my-project"


async def test_validation_closes_its_client(hass):
    client = MagicMock()
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.geodrops.config_flow.make_client", return_value=client), \
         patch("custom_components.geodrops.config_flow.validate_access",
               side_effect=QueryError("503")):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROJECT_ID: "p", const.CONF_CREDENTIALS_JSON: "{}"})
    client.close.assert_called_once()


async def test_probe_lookup_closes_its_client_and_saves_area(hass):
    result = await _at_add_device(hass)
    client = MagicMock()
    with patch("custom_components.geodrops.config_flow.make_client", return_value=client), \
         patch("custom_components.geodrops.config_flow.lookup_serial", return_value=_reading()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {const.DEV_SERIAL: "AAA111", const.DEV_NAME: "Front", const.DEV_AREA: "garden"})
    client.close.assert_called_once()
    assert result["options"][const.CONF_DEVICES] == [
        {"serial": "AAA111", "device_id": 1001, "name": "Front", "area_id": "garden"}]


@pytest.mark.parametrize(("exc", "error"), [
    (QueryError("503"), "cannot_connect"),
    (AuthError("invalid_grant"), "invalid_auth"),
])
async def test_probe_lookup_errors(hass, exc, error):
    result = await _at_add_device(hass)
    with patch("custom_components.geodrops.config_flow.make_client", return_value=MagicMock()), \
         patch("custom_components.geodrops.config_flow.lookup_serial", side_effect=exc):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.DEV_SERIAL: "AAA111", const.DEV_NAME: "Front"})
    assert result["step_id"] == "add_device"
    assert result["errors"] == {"base": error}

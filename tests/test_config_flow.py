from aiogeodrops import (
    DeviceReading,
    GeoDropsAuthError,
    GeoDropsConnectionError,
    GeoDropsCredentialsError,
    GeoDropsQueryError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.geodrops import const
from homeassistant import config_entries, data_entry_flow
from tests.common import FakeGeoDropsClient, patch_client, patch_client_init

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


def _reading(device_id=1001):
    return DeviceReading(
        device_id=device_id,
        sync_delay_hours=1.0,
        moisture_index=2,
        moisture_pct=42.0,
        moisture_d1=42.0,
        moisture_d2=42.0,
        moisture_d3=42.0,
        temp_surface=20.0,
        temp_d1=20.0,
        temp_d2=20.0,
        temp_d3=20.0,
        battery_pct=90.0,
        sun_7d=5.0,
        qcn_d1=2,
        qcn_d2=2,
        qcn_d3=2,
    )


def _known_probe():
    return patch_client("lookup_serial", return_value=_reading())


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _submit_key(hass, flow_id, project="p", key='{"type":"x"}'):
    return await hass.config_entries.flow.async_configure(
        flow_id, {const.CONF_PROJECT_ID: project, const.CONF_CREDENTIALS_JSON: key}
    )


async def _submit_probe(hass, flow_id, serial="AAA111", **extra):
    return await hass.config_entries.flow.async_configure(
        flow_id, {const.DEV_SERIAL: serial, const.DEV_NAME: "Front", **extra}
    )


async def _assert_recovers_to_entry(hass, result):
    """After an error on the credentials step, fixing the input still creates the entry."""
    result = await _submit_key(hass, result["flow_id"])
    assert result["step_id"] == "add_device"
    assert result["errors"] == {}
    with _known_probe():
        result = await _submit_probe(hass, result["flow_id"])
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_full_flow_creates_entry(hass):
    result = await _start(hass)
    assert result["step_id"] == "user"

    result = await _submit_key(
        hass,
        result["flow_id"],
        project="your-gcp-project-id",
        key='{"type":"service_account"}',
    )
    assert result["step_id"] == "add_device"

    with _known_probe() as lookup:
        result = await _submit_probe(hass, result["flow_id"], serial="aaa111 ")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    lookup.assert_awaited_once_with("AAA111", const.DEFAULT_LOOKBACK_HOURS)
    devices = result["options"][const.CONF_DEVICES]
    assert devices[0][const.DEV_SERIAL] == "AAA111"  # normalized
    assert devices[0][const.DEV_ID] == 1001
    assert FakeGeoDropsClient.created[0] == (
        "your-gcp-project-id",
        '{"type":"service_account"}',
    )


async def test_bad_credentials_shows_error(hass):
    result = await _start(hass)
    with patch_client_init(GeoDropsCredentialsError("bad")):
        result = await _submit_key(hass, result["flow_id"], key="not json")
    assert result["errors"] == {"base": "invalid_credentials"}
    await _assert_recovers_to_entry(hass, result)


async def test_unknown_serial_shows_error(hass):
    result = await _submit_key(hass, (await _start(hass))["flow_id"])
    result = await _submit_probe(
        hass, result["flow_id"], serial="ZZZ999"
    )  # lookup: None
    assert result["errors"] == {"base": "device_not_found"}
    with _known_probe():
        result = await _submit_probe(hass, result["flow_id"])
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


def _existing_entry(hass, project="p", key='{"type":"old"}'):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        unique_id=project,
        data={const.CONF_PROJECT_ID: project, const.CONF_CREDENTIALS_JSON: key},
        options={
            const.CONF_DEVICES: [
                {"serial": "AAA111", "device_id": 1001, "name": "Front"}
            ]
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (GeoDropsAuthError("invalid_grant"), "invalid_auth"),
        (GeoDropsConnectionError("503"), "cannot_connect"),
        (GeoDropsQueryError("404 project not found"), "cannot_connect"),
        (RuntimeError("bug"), "unknown"),
    ],
)
async def test_key_check_errors_in_user_step(hass, exc, error):
    result = await _start(hass)
    with patch_client("validate_access", side_effect=exc):
        result = await _submit_key(hass, result["flow_id"])
    assert result["errors"] == {"base": error}
    await _assert_recovers_to_entry(hass, result)


async def test_reauth_replaces_key_and_keeps_probes(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["project_id"] == "p"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"new"}'}
    )
    await hass.async_block_till_done()  # let the triggered reload finish
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"new"}'
    assert entry.data[const.CONF_PROJECT_ID] == "p"
    assert len(entry.options[const.CONF_DEVICES]) == 1


async def test_reauth_with_another_rejected_key_shows_error(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reauth_flow(hass)
    with patch_client(
        "validate_access", side_effect=GeoDropsAuthError("invalid_grant")
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"also-dead"}'}
        )
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"old"}'  # untouched

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_CREDENTIALS_JSON: '{"type":"new"}'}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"new"}'


async def test_reconfigure_blank_key_keeps_stored_key(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROJECT_ID: "new-project"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert FakeGeoDropsClient.created == [("new-project", '{"type":"old"}')]
    assert entry.data == {
        const.CONF_PROJECT_ID: "new-project",
        const.CONF_CREDENTIALS_JSON: '{"type":"old"}',
    }
    assert entry.unique_id == "new-project"
    assert len(entry.options[const.CONF_DEVICES]) == 1


async def test_reconfigure_rotates_key(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await _submit_key(hass, result["flow_id"], key='{"type":"new"}')
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_CREDENTIALS_JSON] == '{"type":"new"}'
    assert entry.unique_id == "p"


async def test_reconfigure_to_already_configured_project_aborts(hass):
    entry = _existing_entry(hass, project="p")
    _existing_entry(hass, project="other")
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROJECT_ID: "other"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[const.CONF_PROJECT_ID] == "p"


async def test_reconfigure_bad_project_shows_error(hass):
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch_client(
        "validate_access", side_effect=GeoDropsQueryError("404 project not found")
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROJECT_ID: "typo-project"}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[const.CONF_PROJECT_ID] == "p"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROJECT_ID: "right-project"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_PROJECT_ID] == "right-project"


async def test_first_probe_search_widens_when_not_found(hass):
    result = await _at_add_device(hass)
    with patch_client("lookup_serial", side_effect=[None, _reading()]) as lookup:
        result = await _submit_probe(hass, result["flow_id"])
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert [c.args for c in lookup.await_args_list] == [
        ("AAA111", const.DEFAULT_LOOKBACK_HOURS),
        ("AAA111", const.MAX_LOOKBACK_HOURS),
    ]


async def test_first_probe_found_in_the_default_window_queries_once(hass):
    result = await _at_add_device(hass)
    with _known_probe() as lookup:
        await _submit_probe(hass, result["flow_id"])
    lookup.assert_awaited_once_with("AAA111", const.DEFAULT_LOOKBACK_HOURS)


async def _at_add_device(hass, project="p"):
    result = await _submit_key(hass, (await _start(hass))["flow_id"], project=project)
    assert result["step_id"] == "add_device"
    return result


async def test_already_configured_project_aborts_before_asking_for_a_probe(hass):
    _existing_entry(hass, project="p")
    result = await _submit_key(hass, (await _start(hass))["flow_id"], project=" p ")
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert FakeGeoDropsClient.created == []  # no query before the abort


async def test_project_id_is_stripped(hass):
    result = await _at_add_device(hass, project="  my-project \n")
    with _known_probe():
        result = await _submit_probe(hass, result["flow_id"])
    assert result["data"][const.CONF_PROJECT_ID] == "my-project"
    assert result["result"].unique_id == "my-project"


async def test_probe_area_is_saved(hass):
    result = await _at_add_device(hass)
    with _known_probe():
        result = await _submit_probe(
            hass, result["flow_id"], **{const.DEV_AREA: "garden"}
        )
    assert result["options"][const.CONF_DEVICES] == [
        {"serial": "AAA111", "device_id": 1001, "name": "Front", "area_id": "garden"}
    ]


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (GeoDropsConnectionError("503"), "cannot_connect"),
        (GeoDropsAuthError("invalid_grant"), "invalid_auth"),
        (RuntimeError("bug"), "unknown"),
    ],
)
async def test_probe_lookup_errors(hass, exc, error):
    result = await _at_add_device(hass)
    with patch_client("lookup_serial", side_effect=exc):
        result = await _submit_probe(hass, result["flow_id"])
    assert result["step_id"] == "add_device"
    assert result["errors"] == {"base": error}
    with _known_probe():
        result = await _submit_probe(hass, result["flow_id"])
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

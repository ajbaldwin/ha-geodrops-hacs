"""Config flow for GeoDrops."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, AreaSelector

from . import const
from .bigquery_api import (
    make_client, lookup_serial, validate_access, AuthError, CredentialsError, QueryError,
)


def _credentials_field():
    return TextSelector(TextSelectorConfig(multiline=True))


async def _validate_credentials(hass, project_id, credentials_json):
    """Build a client and prove it can query. Returns (client, error_key)."""
    try:
        client = await hass.async_add_executor_job(make_client, project_id, credentials_json)
    except CredentialsError:
        return None, "invalid_credentials"
    try:
        await hass.async_add_executor_job(validate_access, client)
    except AuthError:
        return None, "invalid_auth"
    except QueryError:
        return None, "cannot_connect"
    return client, None


class GeoDropsConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    VERSION = 1

    def __init__(self):
        self._project_id = None
        self._credentials_json = None
        self._client = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            client, error = await _validate_credentials(
                self.hass, user_input[const.CONF_PROJECT_ID],
                user_input[const.CONF_CREDENTIALS_JSON])
            if error:
                errors["base"] = error
            else:
                self._project_id = user_input[const.CONF_PROJECT_ID]
                self._credentials_json = user_input[const.CONF_CREDENTIALS_JSON]
                self._client = client
                return await self.async_step_add_device()
        schema = vol.Schema({
            vol.Required(const.CONF_PROJECT_ID): str,
            vol.Required(const.CONF_CREDENTIALS_JSON): _credentials_field(),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_add_device(self, user_input=None):
        errors = {}
        description_placeholders = {}
        if user_input is not None:
            serial = user_input[const.DEV_SERIAL].strip().upper()
            try:
                reading = await self.hass.async_add_executor_job(
                    lookup_serial, self._client, serial, const.DEFAULT_LOOKBACK_HOURS)
            except QueryError:
                errors["base"] = "cannot_connect"
                reading = None
            if not errors and reading is None:
                errors["base"] = "device_not_found"
            if not errors:
                await self.async_set_unique_id(self._project_id)
                self._abort_if_unique_id_configured()
                device = {
                    const.DEV_SERIAL: serial,
                    const.DEV_ID: reading.device_id,
                    const.DEV_NAME: user_input[const.DEV_NAME],
                }
                if user_input.get(const.DEV_AREA):
                    device[const.DEV_AREA] = user_input[const.DEV_AREA]
                return self.async_create_entry(
                    title="GeoDrops",
                    data={const.CONF_PROJECT_ID: self._project_id,
                          const.CONF_CREDENTIALS_JSON: self._credentials_json},
                    options={const.CONF_DEVICES: [device]},
                )
        schema = vol.Schema({
            vol.Required(const.DEV_SERIAL): str,
            vol.Required(const.DEV_NAME): str,
            vol.Optional(const.DEV_AREA): AreaSelector(),
        })
        return self.async_show_form(step_id="add_device", data_schema=schema,
                                    errors=errors, description_placeholders=description_placeholders)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Replace a service-account key that Google has stopped accepting."""
        errors = {}
        entry = self._get_reauth_entry()
        project_id = entry.data[const.CONF_PROJECT_ID]
        if user_input is not None:
            credentials_json = user_input[const.CONF_CREDENTIALS_JSON]
            _, error = await _validate_credentials(self.hass, project_id, credentials_json)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={const.CONF_CREDENTIALS_JSON: credentials_json})
        schema = vol.Schema({vol.Required(const.CONF_CREDENTIALS_JSON): _credentials_field()})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors,
            description_placeholders={"project_id": project_id})

    async def async_step_reconfigure(self, user_input=None):
        """Change the GCP project and/or rotate the key without re-adding probes."""
        errors = {}
        entry = self._get_reconfigure_entry()
        current_project = entry.data[const.CONF_PROJECT_ID]
        if user_input is not None:
            project_id = user_input[const.CONF_PROJECT_ID].strip()
            # blank key field = keep the stored key
            credentials_json = (user_input.get(const.CONF_CREDENTIALS_JSON) or "").strip() \
                or entry.data[const.CONF_CREDENTIALS_JSON]
            if project_id != current_project:
                await self.async_set_unique_id(project_id)
                self._abort_if_unique_id_configured()
            _, error = await _validate_credentials(self.hass, project_id, credentials_json)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, unique_id=project_id,
                    data_updates={const.CONF_PROJECT_ID: project_id,
                                  const.CONF_CREDENTIALS_JSON: credentials_json})
        schema = vol.Schema({
            vol.Required(const.CONF_PROJECT_ID, default=current_project): str,
            vol.Optional(const.CONF_CREDENTIALS_JSON): _credentials_field(),
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GeoDropsOptionsFlow(config_entry)


def _rebuild_client(hass, entry):
    return hass.async_add_executor_job(
        make_client, entry.data[const.CONF_PROJECT_ID], entry.data[const.CONF_CREDENTIALS_JSON])


class GeoDropsOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    def _devices(self):
        return list(self.entry.options.get(const.CONF_DEVICES, []))

    def _save(self, options):
        return self.async_create_entry(title="", data=options)

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "remove_device", "settings"],
        )

    async def async_step_add_device(self, user_input=None):
        errors = {}
        if user_input is not None:
            serial = user_input[const.DEV_SERIAL].strip().upper()
            devices = self._devices()
            if any(d[const.DEV_SERIAL] == serial for d in devices):
                errors["base"] = "duplicate_device"
            else:
                try:
                    client = await _rebuild_client(self.hass, self.entry)
                except CredentialsError:
                    errors["base"] = "cannot_connect"
                    client = None
                if not errors:
                    try:
                        reading = await self.hass.async_add_executor_job(
                            lookup_serial, client, serial, const.DEFAULT_LOOKBACK_HOURS)
                    except AuthError:
                        errors["base"] = "invalid_auth"
                        reading = None
                    except QueryError:
                        errors["base"] = "cannot_connect"
                        reading = None
                    if not errors and reading is None:
                        errors["base"] = "device_not_found"
                    if not errors:
                        device = {const.DEV_SERIAL: serial, const.DEV_ID: reading.device_id,
                                  const.DEV_NAME: user_input[const.DEV_NAME]}
                        if user_input.get(const.DEV_AREA):
                            device[const.DEV_AREA] = user_input[const.DEV_AREA]
                        devices.append(device)
                        options = {**self.entry.options, const.CONF_DEVICES: devices}
                        return self._save(options)
        schema = vol.Schema({
            vol.Required(const.DEV_SERIAL): str,
            vol.Required(const.DEV_NAME): str,
            vol.Optional(const.DEV_AREA): AreaSelector(),
        })
        return self.async_show_form(step_id="add_device", data_schema=schema, errors=errors)

    async def async_step_remove_device(self, user_input=None):
        devices = self._devices()
        if user_input is not None:
            serial = user_input["device"]
            remaining = [d for d in devices if d[const.DEV_SERIAL] != serial]
            registry = dr.async_get(self.hass)
            device = registry.async_get_device(identifiers={(const.DOMAIN, serial)})
            if device is not None:
                registry.async_remove_device(device.id)
            options = {**self.entry.options, const.CONF_DEVICES: remaining}
            return self._save(options)
        choices = {d[const.DEV_SERIAL]: f"{d[const.DEV_NAME]} ({d[const.DEV_SERIAL]})" for d in devices}
        schema = vol.Schema({vol.Required("device"): vol.In(choices)})
        return self.async_show_form(step_id="remove_device", data_schema=schema)

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            options = {**self.entry.options, **user_input}
            return self._save(options)
        opts = self.entry.options
        schema = vol.Schema({
            vol.Required(const.CONF_SCAN_INTERVAL,
                         default=opts.get(const.CONF_SCAN_INTERVAL, const.DEFAULT_SCAN_INTERVAL)): int,
            vol.Required(const.CONF_LOOKBACK_HOURS,
                         default=opts.get(const.CONF_LOOKBACK_HOURS, const.DEFAULT_LOOKBACK_HOURS)): int,
            vol.Required(const.CONF_WARN_HOURS,
                         default=opts.get(const.CONF_WARN_HOURS, const.DEFAULT_WARN_HOURS)): int,
            vol.Required(const.CONF_SKIP_HOURS,
                         default=opts.get(const.CONF_SKIP_HOURS, const.DEFAULT_SKIP_HOURS)): int,
            vol.Required(const.CONF_EXPIRE_MINUTES,
                         default=opts.get(const.CONF_EXPIRE_MINUTES, const.DEFAULT_EXPIRE_MINUTES)): int,
        })
        return self.async_show_form(step_id="settings", data_schema=schema)

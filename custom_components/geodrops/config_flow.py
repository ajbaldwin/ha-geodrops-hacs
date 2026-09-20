"""Config flow for GeoDrops."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from . import const
from .bigquery_api import make_client, fetch_latest, lookup_serial, CredentialsError, QueryError


class GeoDropsConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    VERSION = 1

    def __init__(self):
        self._project_id = None
        self._credentials_json = None
        self._client = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = await self.hass.async_add_executor_job(
                    make_client, user_input[const.CONF_PROJECT_ID],
                    user_input[const.CONF_CREDENTIALS_JSON])
            except CredentialsError:
                errors["base"] = "invalid_credentials"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        fetch_latest, client, [], const.DEFAULT_LOOKBACK_HOURS)
                except QueryError:
                    errors["base"] = "cannot_connect"
                if not errors:
                    self._project_id = user_input[const.CONF_PROJECT_ID]
                    self._credentials_json = user_input[const.CONF_CREDENTIALS_JSON]
                    self._client = client
                    return await self.async_step_add_device()
        schema = vol.Schema({
            vol.Required(const.CONF_PROJECT_ID): str,
            vol.Required(const.CONF_CREDENTIALS_JSON): str,
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
                return self.async_create_entry(
                    title="GeoDrops Soil Moisture",
                    data={const.CONF_PROJECT_ID: self._project_id,
                          const.CONF_CREDENTIALS_JSON: self._credentials_json},
                    options={const.CONF_DEVICES: [{
                        const.DEV_SERIAL: serial,
                        const.DEV_ID: reading.device_id,
                        const.DEV_NAME: user_input[const.DEV_NAME],
                    }]},
                )
        schema = vol.Schema({
            vol.Required(const.DEV_SERIAL): str,
            vol.Required(const.DEV_NAME): str,
        })
        return self.async_show_form(step_id="add_device", data_schema=schema,
                                    errors=errors, description_placeholders=description_placeholders)

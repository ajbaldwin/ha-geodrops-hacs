"""GeoDrops integration setup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from . import const
from .bigquery_api import make_client, CredentialsError
from .coordinator import GeoDropsCoordinator

PLATFORMS = [Platform.SENSOR]

type GeoDropsConfigEntry = ConfigEntry[GeoDropsCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GeoDropsConfigEntry) -> bool:
    try:
        client = await hass.async_add_executor_job(
            make_client,
            entry.data[const.CONF_PROJECT_ID],
            entry.data[const.CONF_CREDENTIALS_JSON],
        )
    except CredentialsError as err:
        # the stored key can't even be parsed; retrying won't fix it
        raise ConfigEntryAuthFailed(str(err)) from err

    coordinator = GeoDropsCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # setup retries with a fresh client, so don't leak this one's HTTP session
        await hass.async_add_executor_job(client.close)
        raise

    # Options changes reload through the options flow (OptionsFlowWithReload)
    # and key/project changes through async_update_reload_and_abort, so no
    # update listener: one would reload a second time.
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GeoDropsConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded

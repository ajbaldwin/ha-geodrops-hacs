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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        client = await hass.async_add_executor_job(
            make_client,
            entry.data[const.CONF_PROJECT_ID],
            entry.data[const.CONF_CREDENTIALS_JSON],
        )
    except CredentialsError as err:
        raise ConfigEntryAuthFailed(str(err)) from err

    coordinator = GeoDropsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[const.DOMAIN].pop(entry.entry_id, None)
    return unloaded

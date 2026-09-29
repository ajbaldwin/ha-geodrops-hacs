"""GeoDrops integration setup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

from . import const
from .bigquery_api import make_client, CredentialsError
from .coordinator import GeoDropsCoordinator, access_denied_issue_id

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
        raise ConfigEntryAuthFailed(
            translation_domain=const.DOMAIN, translation_key="invalid_credentials",
            translation_placeholders={"error": str(err)}) from err

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


async def async_remove_entry(hass: HomeAssistant, entry: GeoDropsConfigEntry) -> None:
    ir.async_delete_issue(hass, const.DOMAIN, access_denied_issue_id(entry.entry_id))


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: GeoDropsConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Let the user delete a probe from its device page.

    Probes are only ever added by the user, so there is no way to tell a dead
    probe from a quiet one; removal is theirs to decide. Dropping it from the
    options keeps it from coming back on the next reload.
    """
    serials = {ident for domain, ident in device_entry.identifiers if domain == const.DOMAIN}
    devices = entry.options.get(const.CONF_DEVICES, [])
    remaining = [d for d in devices if d[const.DEV_SERIAL] not in serials]
    if len(remaining) != len(devices):
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, const.CONF_DEVICES: remaining})
    return True

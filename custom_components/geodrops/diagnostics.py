"""Diagnostics for GeoDrops."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GeoDropsConfigEntry
from . import const

# The key is a credential; the project id identifies the user's GCP account
TO_REDACT = {const.CONF_CREDENTIALS_JSON, const.CONF_PROJECT_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GeoDropsConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    last_exception = None
    if (err := coordinator.last_exception) is not None:
        # Google's error text names the project, e.g. in the job URL
        last_exception = f"{type(err).__name__}: {err}".replace(
            entry.data[const.CONF_PROJECT_ID], "**REDACTED**")
    probes = {}
    for device in entry.options.get(const.CONF_DEVICES, []):
        device_id = device[const.DEV_ID]
        reading = coordinator.reading(device_id)
        seen = coordinator.reading_time(device_id)
        probes[device[const.DEV_SERIAL]] = {
            "device_id": device_id,
            "last_seen_in_poll": seen.isoformat() if seen else None,
            "reading": asdict(reading) if reading else None,
        }
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": last_exception,
            "update_interval_seconds": coordinator.update_interval.total_seconds(),
        },
        "probes": probes,
    }

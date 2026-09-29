"""Diagnostics for GeoDrops."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import const
from .coordinator import GeoDropsConfigEntry

# The key is a credential; the project id identifies the user's GCP account.
TO_REDACT = {const.CONF_CREDENTIALS_JSON, const.CONF_PROJECT_ID}
REDACTED = "**REDACTED**"


def _identifiers(entry: GeoDropsConfigEntry) -> list[str]:
    """Return strings that identify the user's GCP account.

    Google's error text can name the query project (e.g. in a job URL) and the
    service account, whose email names the project the key was made in.
    """
    found = [entry.data[const.CONF_PROJECT_ID]]
    try:
        key = json.loads(entry.data[const.CONF_CREDENTIALS_JSON])
    except ValueError:
        return found
    if isinstance(key, dict):
        found += [
            value
            for field in ("client_email", "project_id")
            if isinstance(value := key.get(field), str) and value
        ]
    # Longest first, so an email is redacted before the project inside it.
    return sorted(found, key=len, reverse=True)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GeoDropsConfigEntry
) -> dict[str, Any]:
    """Return settings, poll status and each probe's last reading."""
    coordinator = entry.runtime_data
    last_exception: str | None = None
    if (err := coordinator.last_exception) is not None:
        last_exception = f"{type(err).__name__}: {err}"
        for identifier in _identifiers(entry):
            last_exception = last_exception.replace(identifier, REDACTED)
    probes: dict[str, dict[str, Any]] = {}
    for device in coordinator.devices:
        device_id = device[const.DEV_ID]
        reading = coordinator.reading(device_id)
        seen = coordinator.reading_time(device_id)
        probes[device[const.DEV_SERIAL]] = {
            "device_id": device_id,
            "last_seen_in_poll": seen.isoformat() if seen else None,
            "reading": asdict(reading) if reading else None,
        }
    interval = coordinator.update_interval
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": last_exception,
            "update_interval_seconds": interval.total_seconds() if interval else None,
        },
        "probes": probes,
    }

"""Polling coordinator for GeoDrops probe readings."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from aiogeodrops import (
    DeviceReading,
    GeoDropsAccessDeniedError,
    GeoDropsAuthError,
    GeoDropsClient,
    GeoDropsError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import const
from .const import DeviceConfig
from .transform import classify_staleness, data_age_hours

_LOGGER = logging.getLogger(__name__)

TROUBLESHOOTING_URL = "https://github.com/ajbaldwin/ha-geodrops-hacs#troubleshooting"

type GeoDropsConfigEntry = ConfigEntry[GeoDropsCoordinator]


def access_denied_issue_id(entry_id: str) -> str:
    """Return the id of the entry's "access denied" repair issue."""
    return f"access_denied_{entry_id}"


class GeoDropsCoordinator(DataUpdateCoordinator[dict[int, DeviceReading]]):
    """Polls every configured probe's latest reading in one query."""

    config_entry: GeoDropsConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: GeoDropsConfigEntry, client: GeoDropsClient
    ) -> None:
        """Poll with `client` at the entry's interval."""
        self.client = client
        # When each device's row last came back from a poll. A poll can succeed
        # yet return no row for a device (GeoDrops' table is briefly empty twice
        # a day), so availability is judged per device, not per poll.
        self._seen: dict[int, datetime] = {}
        # Probes already logged as stale, so "warn after" logs once per episode.
        self._stale: set[int] = set()
        interval: int = entry.options.get(
            const.CONF_SCAN_INTERVAL, const.DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name="GeoDrops",
            config_entry=entry,
            update_interval=timedelta(minutes=interval),
        )

    @property
    def devices(self) -> list[DeviceConfig]:
        """The probes configured in the entry's options."""
        devices: list[DeviceConfig] = self.config_entry.options.get(
            const.CONF_DEVICES, []
        )
        return devices

    @property
    def device_ids(self) -> list[int]:
        """GeoDrops device ids of the configured probes."""
        return [d[const.DEV_ID] for d in self.devices]

    @property
    def lookback_hours(self) -> int:
        """How far back a poll looks for each probe's latest reading."""
        hours: int = self.config_entry.options.get(
            const.CONF_LOOKBACK_HOURS, const.DEFAULT_LOOKBACK_HOURS
        )
        return hours

    def reading(self, device_id: int) -> DeviceReading | None:
        """Return a probe's latest reading, or None if none has arrived yet."""
        return (self.data or {}).get(device_id)

    def reading_time(self, device_id: int) -> datetime | None:
        """Return when a poll last returned a row for this probe."""
        return self._seen.get(device_id)

    async def _async_update_data(self) -> dict[int, DeviceReading]:
        ids = self.device_ids
        if not ids:
            self._seen = {}
            self._clear_access_denied()
            return {}
        try:
            data = await self.client.fetch_latest(ids, self.lookback_hours)
        except GeoDropsAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=const.DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except GeoDropsAccessDeniedError as err:
            self._raise_access_denied(err)
            raise UpdateFailed(
                translation_domain=const.DOMAIN,
                translation_key="access_denied",
                translation_placeholders={"error": str(err)},
            ) from err
        except GeoDropsError as err:
            raise UpdateFailed(
                translation_domain=const.DOMAIN,
                translation_key="query_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._clear_access_denied()
        now = dt_util.utcnow()
        for device_id in data:
            self._seen[device_id] = now
        # A device missing from this poll keeps its last reading; the sensors'
        # expire window decides when that is too old to show.
        previous = self.data or {}
        merged: dict[int, DeviceReading] = {}
        for device_id in ids:
            reading = data.get(device_id, previous.get(device_id))
            if reading is not None:
                merged[device_id] = reading
        self._seen = {d: t for d, t in self._seen.items() if d in ids}
        self._log_staleness(merged, now)
        return merged

    def _raise_access_denied(self, err: GeoDropsAccessDeniedError) -> None:
        """Only a change in GCP fixes a 403, so tell the user in Repairs."""
        ir.async_create_issue(
            self.hass,
            const.DOMAIN,
            access_denied_issue_id(self.config_entry.entry_id),
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="access_denied",
            translation_placeholders={
                "project_id": self.config_entry.data[const.CONF_PROJECT_ID],
                "error": str(err),
            },
            learn_more_url=TROUBLESHOOTING_URL,
        )

    def _clear_access_denied(self) -> None:
        """Remove the repair issue once a poll succeeds."""
        ir.async_delete_issue(
            self.hass, const.DOMAIN, access_denied_issue_id(self.config_entry.entry_id)
        )

    def _log_staleness(self, readings: dict[int, DeviceReading], now: datetime) -> None:
        """Warn once when a probe's data passes "warn after"; note when it recovers."""
        options = self.config_entry.options
        warn: int = options.get(const.CONF_WARN_HOURS, const.DEFAULT_WARN_HOURS)
        skip: int = options.get(const.CONF_SKIP_HOURS, const.DEFAULT_SKIP_HOURS)
        for device in self.devices:
            device_id = device[const.DEV_ID]
            reading = readings.get(device_id)
            age = None if reading is None else data_age_hours(reading, now)
            stale = age is not None and classify_staleness(age, warn, skip) != "ok"
            if stale and device_id not in self._stale:
                self._stale.add(device_id)
                _LOGGER.warning(
                    "Probe %s (%s) has not reported for %.1f hours "
                    "(warn after %s hours)",
                    device[const.DEV_NAME],
                    device[const.DEV_SERIAL],
                    age,
                    warn,
                )
            elif not stale and device_id in self._stale and age is not None:
                self._stale.discard(device_id)
                _LOGGER.info(
                    "Probe %s (%s) is reporting again",
                    device[const.DEV_NAME],
                    device[const.DEV_SERIAL],
                )

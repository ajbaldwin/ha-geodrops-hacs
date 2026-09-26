"""Polling coordinator for GeoDrops BigQuery data."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .bigquery_api import fetch_latest, AuthError, QueryError
from . import const

_LOGGER = logging.getLogger(__name__)


class GeoDropsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.entry = entry
        self.client = client
        # When each device's row last came back from a poll. A poll can succeed
        # yet return no row for a device (GeoDrops' table is briefly empty twice
        # a day), so availability is judged per device, not per poll.
        self._seen = {}
        interval = entry.options.get(const.CONF_SCAN_INTERVAL, const.DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass, _LOGGER, name="GeoDrops", config_entry=entry,
            update_interval=timedelta(minutes=interval),
        )

    @property
    def device_ids(self):
        return [d[const.DEV_ID] for d in self.entry.options.get(const.CONF_DEVICES, [])]

    @property
    def lookback_hours(self):
        return self.entry.options.get(const.CONF_LOOKBACK_HOURS, const.DEFAULT_LOOKBACK_HOURS)

    def reading(self, device_id):
        return (self.data or {}).get(device_id)

    def reading_time(self, device_id):
        return self._seen.get(device_id)

    async def _async_update_data(self):
        ids = self.device_ids
        if not ids:
            self._seen = {}
            return {}
        try:
            data = await self.hass.async_add_executor_job(
                fetch_latest, self.client, ids, self.lookback_hours
            )
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except QueryError as err:
            raise UpdateFailed(str(err)) from err
        now = dt_util.utcnow()
        for device_id in data:
            self._seen[device_id] = now
        # A device missing from this poll keeps its last reading; the sensors'
        # expire window decides when that is too old to show.
        previous = self.data or {}
        merged = {}
        for device_id in ids:
            reading = data.get(device_id, previous.get(device_id))
            if reading is not None:
                merged[device_id] = reading
        self._seen = {d: t for d, t in self._seen.items() if d in ids}
        return merged

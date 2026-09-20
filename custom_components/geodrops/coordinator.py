"""Polling coordinator for GeoDrops BigQuery data."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bigquery_api import fetch_latest, QueryError
from . import const

_LOGGER = logging.getLogger(__name__)


class GeoDropsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.entry = entry
        self.client = client
        interval = entry.options.get(const.CONF_SCAN_INTERVAL, const.DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass, _LOGGER, name="GeoDrops",
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

    async def _async_update_data(self):
        ids = self.device_ids
        if not ids:
            return {}
        try:
            return await self.hass.async_add_executor_job(
                fetch_latest, self.client, ids, self.lookback_hours
            )
        except QueryError as err:
            raise UpdateFailed(str(err)) from err

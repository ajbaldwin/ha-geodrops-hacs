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
from .transform import (
    MAX_MOISTURE_CODES,
    RECALIBRATION_CODES,
    classify_staleness,
    data_age_hours,
    has_code,
)

_LOGGER = logging.getLogger(__name__)

TROUBLESHOOTING_URL = "https://github.com/ajbaldwin/ha-geodrops-hacs#troubleshooting"

# Per-probe repairs: the issue's translation key, and the nextAction codes
# that raise it. Each one's issue id is "<key>_<entry id>_<serial>".
PROBE_ISSUES = (
    # Moisture stays unknown until the test is first run.
    ("max_moisture_required", MAX_MOISTURE_CODES),
    # The calibration is 75 days old; moisture keeps reporting, degraded.
    ("max_moisture_recalibration", RECALIBRATION_CODES),
)

type GeoDropsConfigEntry = ConfigEntry[GeoDropsCoordinator]


def access_denied_issue_id(entry_id: str) -> str:
    """Return the id of the entry's "access denied" repair issue."""
    return f"access_denied_{entry_id}"


def probe_issue_prefixes(entry_id: str) -> tuple[str, ...]:
    """Return the id prefixes of the entry's per-probe repair issues."""
    return tuple(f"{key}_{entry_id}_" for key, _ in PROBE_ISSUES)


def delete_entry_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Remove every repair issue the entry raised."""
    ir.async_delete_issue(hass, const.DOMAIN, access_denied_issue_id(entry_id))
    prefixes = probe_issue_prefixes(entry_id)
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == const.DOMAIN and issue_id.startswith(prefixes):
            ir.async_delete_issue(hass, const.DOMAIN, issue_id)


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
            self._sync_probe_issues({})
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
        self._sync_probe_issues(merged)
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

    def _sync_probe_issues(self, readings: dict[int, DeviceReading]) -> None:
        """Raise a repair for each probe GeoDrops wants max-moisture calibrated.

        Only the user can run the test, in GeoDrops' app, so it is worth a
        repair. Each issue clears once its code goes away. A probe with no
        reading or no nextAction column keeps its issues as they are.
        """
        entry_id = self.config_entry.entry_id
        wanted: set[str] = set()
        for device in self.devices:
            serial = device[const.DEV_SERIAL]
            reading = readings.get(device[const.DEV_ID])
            for key, codes in PROBE_ISSUES:
                issue_id = f"{key}_{entry_id}_{serial}"
                wanted.add(issue_id)
                needed = (
                    None if reading is None else has_code(reading.next_action, codes)
                )
                if needed:
                    ir.async_create_issue(
                        self.hass,
                        const.DOMAIN,
                        issue_id,
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key=key,
                        translation_placeholders={
                            "name": device[const.DEV_NAME],
                            "serial": serial,
                        },
                        learn_more_url=TROUBLESHOOTING_URL,
                    )
                elif needed is False:
                    ir.async_delete_issue(self.hass, const.DOMAIN, issue_id)
        # Probes removed from the options take their issues with them.
        prefixes = probe_issue_prefixes(entry_id)
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if (
                domain == const.DOMAIN
                and issue_id.startswith(prefixes)
                and issue_id not in wanted
            ):
                ir.async_delete_issue(self.hass, const.DOMAIN, issue_id)

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

"""Constants for the GeoDrops integration."""
from __future__ import annotations

from typing import Final, NotRequired, TypedDict

DOMAIN: Final = "geodrops"

# entry.data keys
CONF_PROJECT_ID: Final = "project_id"
CONF_CREDENTIALS_JSON: Final = "credentials_json"

# entry.options keys
CONF_DEVICES: Final = "devices"          # list[DeviceConfig]
CONF_SCAN_INTERVAL: Final = "scan_interval_minutes"
CONF_LOOKBACK_HOURS: Final = "lookback_hours"
CONF_WARN_HOURS: Final = "staleness_warn_hours"
CONF_SKIP_HOURS: Final = "staleness_skip_hours"
CONF_EXPIRE_MINUTES: Final = "expire_after_minutes"

# per-device dict keys
DEV_SERIAL: Final = "serial"
DEV_ID: Final = "device_id"
DEV_NAME: Final = "name"
DEV_AREA: Final = "area_id"   # optional HA area id assigned at add time

# defaults (from the standalone service)
DEFAULT_SCAN_INTERVAL: Final = 20
DEFAULT_LOOKBACK_HOURS: Final = 12
DEFAULT_WARN_HOURS: Final = 6
DEFAULT_SKIP_HOURS: Final = 12
DEFAULT_EXPIRE_MINUTES: Final = 80


class DeviceConfig(TypedDict):
    """A probe as stored in entry.options[CONF_DEVICES]."""

    serial: str
    device_id: int
    name: str
    area_id: NotRequired[str]

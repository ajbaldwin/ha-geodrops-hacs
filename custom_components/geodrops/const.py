"""Constants for the GeoDrops integration."""
DOMAIN = "geodrops"

BQ_TABLE = "geodrops-prod.db_public.p_sensor_unified"

# entry.data keys
CONF_PROJECT_ID = "project_id"
CONF_CREDENTIALS_JSON = "credentials_json"

# entry.options keys
CONF_DEVICES = "devices"          # list[{"serial","device_id","name"}]
CONF_SCAN_INTERVAL = "scan_interval_minutes"
CONF_LOOKBACK_HOURS = "lookback_hours"
CONF_WARN_HOURS = "staleness_warn_hours"
CONF_SKIP_HOURS = "staleness_skip_hours"
CONF_EXPIRE_MINUTES = "expire_after_minutes"

# per-device dict keys
DEV_SERIAL = "serial"
DEV_ID = "device_id"
DEV_NAME = "name"
DEV_AREA = "area_id"   # optional HA area id assigned at add time

# defaults (from the standalone service)
DEFAULT_SCAN_INTERVAL = 20
DEFAULT_LOOKBACK_HOURS = 12
DEFAULT_WARN_HOURS = 6
DEFAULT_SKIP_HOURS = 12
DEFAULT_EXPIRE_MINUTES = 45

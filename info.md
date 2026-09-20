# GeoDrops

Native Home Assistant integration for GeoDrops soil moisture probes. Reads
your probe readings directly from BigQuery — no MQTT bridge, no separate
sync service — and exposes each probe as a device with 15 sensors
(moisture at 3 depths, temperature at 3 depths + surface, per-depth
reading quality, battery, sync delay, 7-day sun average, and more).

Set up entirely through the UI: paste a service-account JSON key and your
GCP project id, then add each probe by the serial shown in the GeoDrops
app. A live preview confirms the probe before it's added.

Default poll interval is 20 minutes (adjustable), issuing one BigQuery
query per poll covering all configured probes.

See the [README](README.md) for GCP/BigQuery setup prerequisites.

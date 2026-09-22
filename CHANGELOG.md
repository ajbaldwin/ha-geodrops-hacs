# Changelog

## 0.5.1 — Cleaner setup-screen wording
- The setup screen's help text now points to the integration's Documentation link instead of showing a raw URL in the description. No functional change.

## 0.5.0 — First HACS release
- First tagged release, installable and updatable through HACS as a custom repository. Version is aligned with the standalone `ha-geodrops-integration` service (also v0.5.0) so both GeoDrops paths share one number.
- Native integration: reads GeoDrops soil-moisture straight from BigQuery — no MQTT broker, no separate sync service. Each probe becomes a device with 15 sensors.
- UI setup: paste a service-account JSON key and GCP project id, then add probes by serial; optional Home Assistant Area per probe.
- Configurable poll interval (default 20 minutes) plus lookback and staleness thresholds under Advanced Options.

## 0.1.0
- Initial release: native GeoDrops soil-moisture integration.
- UI config flow (paste service-account JSON) + add probes by serial with live preview.
- 15 sensors per probe; polling coordinator with configurable interval and staleness thresholds.

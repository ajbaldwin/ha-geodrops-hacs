# Changelog

## 0.6.0-beta.2 — No more twice-daily "unavailable" blips
- **Probes stay up through GeoDrops' empty polls.** About twice a day GeoDrops' data briefly comes back empty for a poll, and every probe went "unavailable" for 20 minutes even though nothing was wrong. Each probe now keeps its last reading, and goes unavailable only when its own data hasn't arrived for longer than "Expire after" (80 minutes by default). This applies whether the polls failed or just came back empty.

## 0.6.0-beta.1 — Replace a dead key without starting over
- **New key without re-adding probes.** If Google stops accepting your service-account key (deleted, revoked, or its service account disabled), GeoDrops now asks you to re-authenticate on the Devices & Services page — paste a new key and you're back, probes and settings intact. Previously it retried forever and the only fix was deleting and re-adding the integration.
- **Reconfigure.** Change the GCP project or rotate the key any time from the integration's ⋮ menu → Reconfigure. Leave the key blank to keep the current one.
- **Rides out Google hiccups.** Temporary Google errors (outages, rate limits, network drops) no longer trigger a re-authentication prompt; the next poll simply tries again. Permission errors (e.g. a missing BigQuery Job User role) also keep retrying and recover on their own once fixed.
- **No more hung polls.** Each BigQuery query now gives up after about 60 seconds instead of retrying for up to 40 minutes, so setup and "add a probe" fail fast with a clear error during an outage.
- **Fewer false "unavailable" gaps.** The default "Expire after" is now 80 minutes (was 45), so sensors stay up through three missed polls instead of two. If you've ever saved Advanced Options, your stored value is kept — change it under Configure → Advanced Options.

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

# Changelog

## 0.6.0 — Re-authentication, steadier sensors, and a lighter install
Everything since 0.5.1. If you ran the 0.6.0 betas, the only change since beta.7 is the version number.

**⚠️ Before you update**
- **Update automations that check Moisture State or Quality.** These sensors now report stable keys (`moist_plus`, `good`, `training`, …) that the UI still shows as "Moist+", "Good", "Training". Automations and templates comparing against the old text stop matching; the README's "States for automations" table lists every state. An unclassified value is now Home Assistant's own `unknown`.
- **Some sensors move off auto-generated dashboards.** Battery, Sync Delay, Last Reading and Quality Depth 1–3 are now *Diagnostic* sensors: they're listed under *Diagnostic* on the device page and drop off auto-generated dashboards. Entity ids and history are unchanged; add them to a card by hand if you want them there.

**Fixing a broken key**
- **Re-authenticate instead of starting over.** If Google stops accepting your service-account key (deleted, revoked, or its service account disabled), GeoDrops asks you to re-authenticate on the Devices & Services page. Paste a new key and your probes and settings stay as they were.
- **Reconfigure.** Change the GCP project or rotate the key any time from the integration's ⋮ menu → Reconfigure. Leave the key blank to keep the current one.
- **GCP permission problems show in Repairs.** A missing BigQuery role or a disabled BigQuery API raises an issue under Settings → Repairs, linked to the README's troubleshooting section. It clears on its own after the next successful poll.

**Sensors that stay up, and go down when they should**
- **No more twice-daily "unavailable" blips.** About twice a day GeoDrops' data briefly comes back empty. Each probe now keeps its last reading through that, and goes unavailable only when its own data hasn't arrived for longer than "Expire after".
- **"Expire after" defaults to 80 minutes** (was 45), so sensors ride out three missed polls instead of two. A value you saved under Advanced Options is kept.
- **Google hiccups don't need you.** Outages, rate limits and network drops no longer ask you to re-authenticate; the next poll tries again. Each query gives up after about 60 seconds instead of retrying for up to 40 minutes, so setup fails fast with a clear error during an outage.
- **Quiet probes are caught.** A probe goes unavailable once its latest reading is older than "Mark unavailable after", even while GeoDrops keeps serving that same old reading. "Warn after" writes one warning to the log, and a note when the probe reports again.
- **A bad sync delay no longer blanks a probe.** GeoDrops has reported a sync delay of about 2,053 hours on readings only an hour old. A sync delay more than 3 hours longer than the reading's own age is now ignored, and Sync Delay shows `unknown` for it.
- **Missing values show as unknown, not 0.** A probe that doesn't report a temperature or battery no longer shows 0 °C / 0 %, which could trigger frost or low-battery automations.

**New**
- **Last Reading sensor** shows when each probe last took a reading, so each probe now has 16 sensors.
- **Download diagnostics** from the integration's ⋮ menu, for bug reports. The key, the service account's email and your project ids are redacted.
- **Delete a probe from its device page.** Deleting the device also removes the probe from the integration, so it isn't recreated on the next poll.
- **Sync Delay starts disabled on probes you add from now on.** Existing probes keep it as it is; enable it from the device page if you want it.

**Smaller and cleaner**
- **Lighter install, and no grpcio warning from GeoDrops.** GeoDrops reads BigQuery through its own small library, [aiogeodrops](https://github.com/ajbaldwin/aiogeodrops), instead of Google's BigQuery SDK. That removes grpcio, protobuf and the rest of the SDK, along with the "grpcio < 1.83.0 does not support Post-Quantum Cryptography" warning. Polls run on Home Assistant's own event loop instead of a worker thread.
- **Forms check their values and explain errors.** Every field has help text. The poll interval is at least 5 minutes, "Warn after" can't exceed "Mark unavailable after", and "Expire after" must be longer than the poll interval. Pasting JSON that isn't a key file says so, and an unexpected error leaves the form open so you can try again.
- **The README is corrected about the key.** It said Home Assistant stores the key encrypted; it doesn't. Config entries are plain text in `/config/.storage` and in backups. The README now says so, and suggests deleting the downloaded key file and setting a daily BigQuery quota.
- **Docs.** The README gains an Advanced Options reference, automation examples, known limitations, troubleshooting, and removal instructions.

## 0.6.0-beta.7 — Probes no longer blanked by a bad sync delay
- **A probe stays available when GeoDrops reports an impossible sync delay.** On 2026-09-30, GeoDrops' data gave one probe a sync delay of about 2,053 hours (85 days) on readings only an hour old, while the probe kept reporting every 30 minutes. GeoDrops took that at face value and marked all of the probe's sensors unavailable for 6 hours. A sync delay more than 3 hours longer than the reading's own age is now treated as bad data: the probe's age is judged from when the reading was taken instead, and its sensors stay available.
- **Sync Delay shows `unknown` for such a value**, instead of a spike of thousands of hours in its history.
- **Nothing to change on your side.** Poll interval, "Mark unavailable after" and "Expire after" work as before.

## 0.6.0-beta.6 — A lighter, native BigQuery connection
- **Smaller install, and no more grpcio warning from GeoDrops.** GeoDrops now reads BigQuery through its own small library, [aiogeodrops](https://github.com/ajbaldwin/aiogeodrops), instead of Google's BigQuery SDK. That removes grpcio, protobuf and the rest of the SDK from what GeoDrops installs, so the "grpcio < 1.83.0 does not support Post-Quantum Cryptography" warning no longer comes from GeoDrops. Polls also run on Home Assistant's own event loop and HTTP connection instead of a worker thread.
- **Nothing to change on your side.** Sensors, entity IDs, states, options and your stored key are all unchanged. Before this release, readings from the new connection were compared with beta.5 on a live install, and every value matched.
- **Setup survives unexpected errors.** An unexpected error while checking a key or looking up a probe used to end the setup form. Now the form stays open, says to check the log (where the details are), and you can try again.
- **Diagnostics hide more.** Downloaded diagnostics now also redact the service account's email and the project the key was created in, not just the project queries run in.
- **Keeping the key safe.** The README said Home Assistant stores the key encrypted. It doesn't: config entries are kept in plain text in `/config/.storage` and included in backups. The README now says so, and suggests deleting the downloaded key file and setting a daily BigQuery quota to cap the cost if a key ever leaks.
- **Log wording.** The "has not reported for … hours" and "is reporting again" log messages start with "Probe" instead of "GeoDrops probe"; the log line already names the integration.

## 0.6.0-beta.5 — Quality sensors stay on
- **Quality sensors stay enabled on new probes.** beta.4 created Quality Depth 1–3 disabled on newly added probes. A disabled sensor has no state at all, not just a hidden one, so irrigation schedulers and other integrations that check these sensors to decide whether a moisture reading can be trusted would have treated the probe as unreliable. They are enabled again and stay under *Diagnostic* on the device page. Only Sync Delay is disabled by default.

## 0.6.0-beta.4 — Diagnostics, Repairs, and a tidier device page
- **Technical sensors move to the Diagnostic section.** Battery, Sync Delay, Last Reading and Quality Depth 1–3 now appear under *Diagnostic* on the device page and drop off auto-generated dashboards. They keep their entity ids and history; add them to a dashboard card by hand if you want them there.
- **New probes start leaner.** Sync Delay and Quality Depth 1–3 are disabled by default on probes you add from now on. Existing probes keep these sensors as they are. Enable them from the device page if you need them.
- **GCP permission problems show in Repairs.** A missing BigQuery role or a disabled BigQuery API now raises an issue under Settings → Repairs, linked to the README's troubleshooting section. It clears on its own after the next successful poll.
- **Download diagnostics.** The integration's ⋮ menu → Download diagnostics saves settings, poll status, and each probe's last reading for bug reports. The service-account key and project id are redacted.
- **Delete a probe from its device page.** Deleting the device also removes the probe from the integration, so it isn't recreated on the next poll.
- **Clearer forms and errors.** Every setup, add-probe, re-authenticate and reconfigure field has help text, and error messages are translated.
- **Docs.** The README gains an Advanced Options reference, automation examples, known limitations, troubleshooting, and removal instructions.

## 0.6.0-beta.3 — Translated states, a Last Reading sensor, safer settings
- **⚠️ Update automations that check Moisture State or Quality.** These sensors now report stable keys (`moist_plus`, `good`, `training`, …) that the UI still shows as "Moist+", "Good", "Training". Automations and templates comparing against the old text stop matching; the README's "States for automations" table lists every state. An unclassified value is now Home Assistant's own `unknown`.
- **New Last Reading sensor** shows when each probe last took a reading.
- **Missing values show as unknown, not 0.** A probe that doesn't report a temperature or battery no longer shows 0 °C / 0 %, which could trigger frost or low-battery automations.
- **Quiet probes are caught.** A probe now goes unavailable once its latest reading is too old, even while GeoDrops keeps serving that same old reading.
- **"Warn after" works.** A probe past it gets one warning in the Home Assistant log, and a note when it reports again.
- **Advanced Options check their values.** The poll interval is at least 5 minutes, "Warn after" can't exceed "Mark unavailable after", and "Expire after" must be longer than the poll interval. A previously saved value outside these limits keeps working until you next save the form.
- **Clearer setup errors.** Pasting JSON that isn't a key file now says so instead of "Unknown error", and adding an already-configured project stops on the first screen.

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

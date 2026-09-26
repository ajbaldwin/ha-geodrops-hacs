# GeoDrops for Home Assistant

A native Home Assistant integration for [GeoDrops](https://geodrops.io/) soil
moisture probes. It reads your sensor data straight out of BigQuery and
exposes each probe as a Home Assistant device with 16 sensors — no MQTT
bridge, no external service to run, no YAML to hand-edit. Everything is
configured through the UI.

This is a companion project to the standalone
[`ha-geodrops-rachio-irrigation`](https://github.com/ajbaldwin/ha-geodrops-rachio-irrigation)
irrigation scheduler, but it does not require it — install this on its own if
all you want is soil-moisture data in Home Assistant.

## What it does

GeoDrops probes publish their readings to a BigQuery table
(`geodrops-prod.db_public.p_sensor_unified`) that GeoDrops has made publicly
readable. This integration polls that table directly from Home Assistant's
BigQuery client library, on a timer, and turns the latest reading per probe
into sensor entities. There's no MQTT broker, no intermediate sync process,
and no polling service to keep alive outside of Home Assistant itself.

## Prerequisites

You need a Google Cloud Platform (GCP) project of your own — this is where
your queries run and are billed, not where the data lives.

Follow the GeoDrops community walkthrough (with screenshots),
[Integrating GeoDrops soil moisture sensors with Home Assistant](https://geodrops.discourse.group/t/integrating-geodrops-soil-moisture-sensors-with-home-assistant/280#p-953-step-by-step-setup-5), or the
self-contained steps below. If that link ever moves, search the
[GeoDrops community](https://geodrops.discourse.group/) for "Home Assistant".

1. **Create (or reuse) a GCP project** at the
   [GCP Console](https://console.cloud.google.com/) — e.g. `home-assistant-geodrops`.
   Note its **project ID** (you enter it during setup).
2. **Enable the BigQuery API** on that project: APIs & Services → Library →
   search "BigQuery API" → **Enable**.
3. **Create a service account**: IAM & Admin → Service Accounts →
   **Create service account** (e.g. `home-assistant-bigquery`).
4. **Grant it `BigQuery Job User`** (`roles/bigquery.jobUser`) **on your own
   project**. That is the only role required — it lets the account run query
   jobs billed to your project. *(The community guide also adds `BigQuery Data
   Viewer`; that's harmless but not required to read the public `db_public`
   dataset.)*
5. **Create and download a JSON key**: on the service account → Keys → Add key
   → Create new key → **JSON**.
6. **Paste the key's contents into the config flow** at setup (see
   *Configuration* below). Unlike the older MQTT bridge, this integration does
   **not** need the file placed in `/config` — Home Assistant stores it in the
   encrypted config entry.

You do **not** need to request access to GeoDrops' data or add any
reader/viewer grant on the `db_public` dataset — GeoDrops publishes it as a
public dataset, so any service account that can run a query job in its own
project can already read it. If a query ever fails with a permissions error
*after* your Job User role is confirmed, the cause is almost certainly on the
GeoDrops side (dataset sharing changed), not your IAM setup.

## Installation

1. In HACS, add this repository as a **custom repository** (category:
   Integration): `https://github.com/ajbaldwin/ha-geodrops-hacs`.

   This repository publishes releases with `hide_default_branch: true`, so
   HACS will only ever offer you tagged releases, never the tip of `main`.
2. Install **GeoDrops** from HACS, then restart Home Assistant
   when prompted.
3. Go to **Settings → Devices & Services → Add Integration**, search for
   **GeoDrops**, and start the config flow.

### Beta versions

New versions are released as betas (`X.Y.Z-beta.N`) before they become a
stable release. HACS only offers betas if you opt in:

1. Go to **Settings → Devices & services → Entities**, search for
   **Pre-release**, and open the one for *GeoDrops* (a switch HACS creates for
   each repository, disabled by default).
2. Enable the entity, wait about 30 seconds, then turn the switch **on**.

HACS then offers each beta as an update. Turn the switch off to go back to
stable releases only; you'll get the next stable when it's newer than the beta
you're on.

## Configuration

The config flow is two steps:

1. **Credentials.** Paste the full contents of your service-account JSON key
   into the "Service-account JSON" field, and enter your GCP **project id**
   (e.g. `your-gcp-project-id` — this is your own project from the
   prerequisites above, not GeoDrops'). Home Assistant validates the
   credentials by making a real BigQuery call before letting you continue.
2. **Add a probe.** Enter the probe's **serial number** exactly as shown in
   the GeoDrops app (e.g. `AAA111`) and a friendly name. The integration
   looks up recent readings for that serial to confirm it exists and has
   reported within the lookback window before adding it — if nothing turns
   up, you'll get an error instead of a silently-empty device. This lookup
   only validates the serial; it does not show a live reading preview.

After the first probe is added, you can add more, remove existing ones, or
tune polling/staleness settings at any time from the integration's
**Configure** options (Settings → Devices & Services → GeoDrops →
Configure). Adding another probe by serial works the same way as the initial
setup.

### Rotating the key or changing project

To paste a new service-account key or switch GCP projects, open the
integration's menu (Settings → Devices & Services → GeoDrops → ⋮) and choose
**Reconfigure**. Leave the key field blank to keep the current key. Your
probes and settings are kept.

If Google stops accepting the stored key (because it was deleted or revoked,
or its service account was disabled), Home Assistant stops polling and flags
GeoDrops as needing re-authentication on the Devices & Services page. Click
**Reconfigure** on it, then create a new JSON key for the service account and
paste it in to get polling going again. Permission errors (for
example, a missing BigQuery Job User role) don't trigger this. Home Assistant
keeps retrying those, and polling recovers on its own once you fix the role
in GCP.

## Sensors

Each probe becomes one Home Assistant device with 16 sensors:

| Sensor | Description |
| --- | --- |
| Dominant Moisture | Overall moisture reading (%), the probe's headline value |
| Moisture State | Enum classification of the dominant moisture reading (e.g. dry/moist/wet) |
| Moisture Depth 1 | Moisture (%) at depth sensor 1 |
| Moisture Depth 2 | Moisture (%) at depth sensor 2 |
| Moisture Depth 3 | Moisture (%) at depth sensor 3 |
| Quality Depth 1 | Reading-quality classification at depth sensor 1 |
| Quality Depth 2 | Reading-quality classification at depth sensor 2 |
| Quality Depth 3 | Reading-quality classification at depth sensor 3 |
| Battery | Probe battery level (%) |
| Sync Delay | Hours since the probe's last successful sync to GeoDrops |
| Surface Temperature | Soil surface temperature (°C) |
| Temperature Depth 1 | Soil temperature (°C) at depth sensor 1 |
| Temperature Depth 2 | Soil temperature (°C) at depth sensor 2 |
| Temperature Depth 3 | Soil temperature (°C) at depth sensor 3 |
| Avg. 7-Day Sun | 7-day trailing average sun exposure (hours) |
| Last Reading | When the probe took its latest reading (timestamp) |

Moisture-related sensors report `unknown` (rather than a misleading value)
while a probe is still in its factory training period and hasn't produced a
calibrated moisture reading yet. Any other value GeoDrops doesn't report
(for example a missing temperature) shows as `unknown`, never as 0. A probe
whose latest reading is older than the configured "mark unavailable after"
threshold (judged by both its sync delay and the reading's own timestamp)
goes unavailable entirely. Once a probe's data is older than "warn after", a
warning is written to the Home Assistant log (once, until it reports again).

### States for automations

Moisture State and the three Quality sensors show friendly labels in the UI,
but their raw states (what automations, templates and scripts compare
against) are stable keys:

| Sensor | Raw states (UI label) |
| --- | --- |
| Moisture State | `dry` (Dry), `dry_plus` (Dry+), `moist` (Moist), `moist_plus` (Moist+), `wet` (Wet), `wet_plus` (Wet+) |
| Quality Depth 1–3 | `bad` (Bad), `poor` (Poor), `good` (Good), `training` (Training) |

A value GeoDrops doesn't classify is Home Assistant's own `unknown`.

## Polling and cost

The integration issues **one BigQuery query per poll**, covering the latest
reading for *all* configured probes at once — it does not issue one query
per device. The default poll interval is **20 minutes**, adjustable in the
integration's options (Settings → Devices & Services → GeoDrops →
Configure → Advanced Options), along with the lookback window
and staleness thresholds. At this query pattern and a typical handful of
probes, usage stays well within BigQuery's free tier.

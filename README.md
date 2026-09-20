# GeoDrops for Home Assistant

A native Home Assistant integration for [GeoDrops](https://geodrops.io/) soil
moisture probes. It reads your sensor data straight out of BigQuery and
exposes each probe as a Home Assistant device with 15 sensors — no MQTT
bridge, no external service to run, no YAML to hand-edit. Everything is
configured through the UI.

This is a companion project to the standalone
[`ha-geodrops-rachio-wrapper`](https://github.com/ajbaldwin/ha-geodrops-rachio-wrapper)
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

1. **A GCP project.** Create one (or reuse one) at the
   [GCP Console](https://console.cloud.google.com/). Note its **project ID**.
2. **The BigQuery API enabled** on that project (APIs & Services → Library →
   search "BigQuery API" → Enable).
3. **A service account** in that project, with the **BigQuery Job User** role
   (`roles/bigquery.jobUser`) granted **on your own project**. This is the
   only role you need to grant — it lets the service account run query jobs
   billed to your project.
4. **A downloaded JSON key** for that service account (Service account →
   Keys → Add Key → Create new key → JSON). Keep this file safe; you'll paste
   its contents into the config flow during setup, and Home Assistant stores
   it in the config entry, not on disk as a separate file.

You do **not** need to request access to GeoDrops' data, and you do **not**
need any reader/viewer grant on the `db_public` dataset itself — GeoDrops has
published it as a public dataset, so any service account that can run a
query job in its own project can already read it. If a query ever fails with
a permissions error after your Job User role is confirmed, the cause is
almost certainly on the GeoDrops side (dataset sharing changed), not your
IAM setup — check the
[GeoDrops community BigQuery setup thread](https://geodrops.discourse.group/t/integrating-geodrops-soil-moisture-sensors-with-home-assistant/280)
for current status.

## Installation

1. In HACS, add this repository as a **custom repository** (category:
   Integration): `https://github.com/ajbaldwin/ha-geodrops-hacs`.

   This repository publishes releases with `hide_default_branch: true`, so
   HACS will only ever offer you tagged releases, never the tip of `main`.
2. Install **GeoDrops** from HACS, then restart Home Assistant
   when prompted.
3. Go to **Settings → Devices & Services → Add Integration**, search for
   **GeoDrops**, and start the config flow.

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
setup, with the same live preview.

## Sensors

Each probe becomes one Home Assistant device with 15 sensors:

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

Moisture-related sensors report `unknown` (rather than a misleading value)
while a probe is still in its factory training period and hasn't produced a
calibrated moisture reading yet. A probe whose last sync is older than the
configured "mark unavailable after" threshold goes unavailable entirely, and
one past the "warn after" threshold is still reported but flagged as stale.

## Polling and cost

The integration issues **one BigQuery query per poll**, covering the latest
reading for *all* configured probes at once — it does not issue one query
per device. The default poll interval is **20 minutes**, adjustable in the
integration's options (Settings → Devices & Services → GeoDrops →
Configure → Polling & staleness settings), along with the lookback window
and staleness thresholds. At this query pattern and a typical handful of
probes, usage stays well within BigQuery's free tier.

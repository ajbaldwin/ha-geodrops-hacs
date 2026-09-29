# Quality scale roadmap

A self-assessment of the GeoDrops integration against the Home Assistant
[Integration Quality Scale](https://www.home-assistant.io/docs/quality_scale/)
([rule reference](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules))
and the [development guidelines](https://developers.home-assistant.io/docs/development_guidelines/),
with the changes needed to reach Platinum.

Assessed against v0.6.0-beta.3 (commit `8fe1b99`), 2026-09-29.

> The quality scale is only formally awarded to core integrations. For a HACS
> integration this is a self-assessment, but every rule below is applicable
> and is what a core reviewer would check.

## Scorecard

| Tier | Rules | Done | Exempt | To do | Blocking work |
| --- | --- | --- | --- | --- | --- |
| Bronze | 20 | 15 | 5 | 0 | None |
| Silver | 10 | 9 | 1 | 0 | None |
| Gold | 21 | 18 | 3 | 0 | None |
| Platinum | 3 | 2 | 0 | 1 | Strict typing of the integration |

The codebase is in good shape for its tier: runtime data, coordinator,
reauth, reconfigure, translated entity names, icon translations and 100 % test
coverage are in place. Bronze, Silver and Gold are complete. For Platinum, the
async `aiogeodrops` library replaces the BigQuery client; strict typing of the
integration remains.

---

## Bronze

| Rule | Status | Notes |
| --- | --- | --- |
| action-setup | Exempt | No service actions. |
| appropriate-polling | Done | 20 min default, 5 min floor. See [core parity](#core-parity-notes) on the configurable interval. |
| brands | Done | `brand/` icons and logos. |
| common-modules | Done | Coordinator in `coordinator.py`. Add `entity.py` if a second platform appears. |
| config-flow | Done | Every flow field has a `data_description`. |
| config-flow-test-coverage | Done | 100 % covered; every error test resubmits valid input and finishes the flow. |
| dependency-transparency | Done | [`aiogeodrops`](https://github.com/ajbaldwin/aiogeodrops) is MIT, published to PyPI from public CI with trusted publishing. |
| docs-actions | Exempt | No actions. |
| docs-conditions | Exempt | No conditions. |
| docs-triggers | Exempt | No triggers. |
| docs-high-level-description | Done | README "What it does". |
| docs-installation-instructions | Done | README "Prerequisites" and "Installation". |
| docs-removal-instructions | Done | README "Removing the integration". |
| entity-event-setup | Exempt | Entities only use `CoordinatorEntity`; no manual subscriptions. |
| entity-unique-id | Done | `{serial}_{suffix}`. |
| has-entity-name | Done | |
| runtime-data | Done | `GeoDropsConfigEntry = ConfigEntry[GeoDropsCoordinator]`. |
| test-before-configure | Done | `validate_access` runs a real zero-byte query. |
| test-before-setup | Done | `async_config_entry_first_refresh`; bad key raises `ConfigEntryAuthFailed`. |
| unique-config-entry | Done | Unique ID is the GCP project ID. |

### Changes (done)

1. **Field descriptions** (`strings.json`). Add `data_description` for
   `config.step.user` (`project_id`: "Your own GCP project, where queries run
   and are billed, not GeoDrops'"; `credentials_json`: "The full contents of
   the downloaded JSON key file") and for `add_device` in both `config` and
   `options` (`serial`, `name`, `area_id`). Mirror into `translations/en.json`.
2. **Error-recovery tests.** Each error test in `tests/test_config_flow.py`
   (`test_bad_credentials_shows_error`, `test_unknown_serial_shows_error`,
   `test_rejected_key_in_user_step_shows_invalid_auth`,
   `test_probe_lookup_errors`, the reauth and reconfigure error tests)
   must resubmit valid input in the same flow and assert `CREATE_ENTRY` or
   `ABORT`. The rule requires proving the flow recovers, not only that the
   error shows.
3. **Removal docs.** Add a README "Removing the integration" section:
   Settings → Devices & services → GeoDrops → ⋮ → Delete, then remove it from
   HACS, then optionally delete the service-account key and service account
   in GCP (the one step that stops any further billing risk).

---

## Silver

| Rule | Status | Notes |
| --- | --- | --- |
| action-exceptions | Exempt | No actions. |
| config-entry-unloading | Done | Unloads platforms and closes the client. |
| docs-configuration-parameters | Done | README "Advanced Options" table. |
| docs-installation-parameters | Done | Project ID and JSON key are described. |
| entity-unavailable | Done | Per-probe `available` from staleness and expiry. |
| integration-owner | Done | `@ajbaldwin`. |
| log-when-unavailable | Done | Coordinator logs failures once; staleness logs once per episode. |
| parallel-updates | Done | `PARALLEL_UPDATES = 0` in `sensor.py`. |
| reauthentication-flow | Done | `reauth_confirm`. |
| test-coverage | Done | 100 % (CI). |

### Changes (done)

1. **`PARALLEL_UPDATES = 0`** at the top of `sensor.py` (the coordinator does
   all fetching, so entity updates need no limit).
2. **Options table in README.** One row per Advanced Option: name, default,
   range, and effect. Include the cross-field rules ("Warn after" ≤ "Mark
   unavailable after"; "Expire after" > poll interval). The text already
   exists in `strings.json` `data_description`.

---

## Gold

| Rule | Status | Notes |
| --- | --- | --- |
| devices | Done | One device per probe with serial and model. |
| diagnostics | Done | `diagnostics.py`; key and project id redacted, including from the last error. |
| discovery | Exempt | Cloud data source; nothing to discover on the network. |
| discovery-update-info | Exempt | Same. |
| docs-data-update | Done | README "Polling and cost", "Advanced Options" and the availability rules under "Sensors". |
| docs-examples | Done | README "Automation examples". |
| docs-known-limitations | Done | README "Known limitations". |
| docs-supported-devices | Done | README "Supported devices". |
| docs-supported-functions | Done | Sensor tables. |
| docs-troubleshooting | Done | README "Troubleshooting"; the repair issue links to it. |
| docs-use-cases | Done | README "Use cases". |
| dynamic-devices | Exempt | GeoDrops' table is public and shared; there is no per-account device list to watch. Probes are user-declared by serial. |
| entity-category | Done | Battery, Sync Delay, Last Reading, Quality Depth 1–3 are diagnostic. |
| entity-device-class | Done | Sync Delay is a duration. Avg. 7-Day Sun is hours per day, a rate, so it has none. |
| entity-disabled-by-default | Done | Sync Delay, for newly added probes. Quality Depth 1–3 stay enabled: irrigation integrations read their states, and a disabled entity has none. |
| entity-translations | Done | |
| exception-translations | Done | `exceptions` in `strings.json`; every raised HA exception uses a translation key. |
| icon-translations | Done | `icons.json` with state icons. |
| reconfiguration-flow | Done | |
| repair-issues | Done | A non-transient 403 raises an `access_denied` repair, cleared by the next successful poll or on entry removal. |
| stale-devices | Done | Options-flow removal, plus `async_remove_config_entry_device` for the device page. |

### Changes (done)

1. **Diagnostics** (new `diagnostics.py`).
   `async_get_config_entry_diagnostics` returning `entry.data` with
   `credentials_json` and `project_id` passed through `async_redact_data`,
   `entry.options`, coordinator `last_update_success`, `last_exception`, the
   per-probe `_seen` times and the last `DeviceReading`s. Test with a
   `syrupy` snapshot.
2. **Entity metadata** (`sensor.py` `SENSOR_SPECS`).
   - `entity_category=EntityCategory.DIAGNOSTIC`: Battery, Sync Delay,
     Last Reading, Quality Depth 1–3.
   - `entity_registry_enabled_default=False`: Sync Delay. (Quality Depth 1–3
     shipped disabled in 0.6.0-beta.4 and were re-enabled: other integrations
     read their states.)
     This only affects newly added probes; existing entities stay enabled.
   - Sync Delay: `SensorDeviceClass.DURATION`, `UnitOfTime.HOURS`.
     Leave Avg. 7-Day Sun without a device class: it is hours per day, a
     rate, not a duration.
   - Use HA constants `PERCENTAGE` and `UnitOfTemperature.CELSIUS` instead of
     `"%"` and `"°C"`. Add `suggested_display_precision` where GeoDrops
     returns long floats.
3. **Exception translations.** Add an `exceptions` section to `strings.json`
   (`auth_failed`, `query_failed`, each with an `{error}` placeholder) and
   raise with `translation_domain=DOMAIN, translation_key=...,
   translation_placeholders={"error": str(err)}` in `__init__.py` and
   `coordinator.py`.
4. **Repair issue for permission errors.** Split a 403 (`Forbidden`, including
   "BigQuery API has not been used in project") out of `QueryError` as a new
   `AccessDeniedError`. In the coordinator, create an
   `ir.async_create_issue(..., is_fixable=False)` pointing at the README's
   IAM steps, and `ir.async_delete_issue` on the next successful poll. This
   is the case the README already describes as "fix the role in GCP".
5. **Device-page removal.** Implement `async_remove_config_entry_device` in
   `__init__.py`: allow removal, and drop the probe from
   `entry.options[CONF_DEVICES]` so it is not recreated on reload.
6. **Docs** (README):
   - *Use cases*: irrigation gating, frost/soil-temperature alerts, low
     battery notifications.
   - *Examples*: two or three YAML automations, e.g. skip Rachio when
     `sensor.<probe>_moisture_state` is `moist_plus` or wetter; notify when
     Battery < 20.
   - *Supported devices*: GeoDrops Droplet probes visible in
     `db_public.p_sensor_unified`; nothing else.
   - *Known limitations*: data lags by the probe's sync delay; GeoDrops'
     table is briefly empty twice a day; adding a probe only searches the
     last 12 hours; no local API.
   - *Troubleshooting*: `device_not_found`, `cannot_connect` (role, API not
     enabled), reauth, all-`unknown` moisture during training, enabling debug
     logging.

**Optional refactor: probes as config subentries.** Config subentries give
each probe a native "Add probe" button, its own reconfigure, and delete that
also removes its device and entities. That would replace the add/remove menu
in the options flow and satisfy `stale-devices` fully. It needs
`VERSION = 2` and an `async_migrate_entry` that moves `options["devices"]`
into subentries. Entity unique IDs are serial-based, so entities survive.
Worth doing if the options flow grows; not required for Gold.

---

## Platinum

| Rule | Status | Notes |
| --- | --- | --- |
| async-dependency | Done | [`aiogeodrops`](https://github.com/ajbaldwin/aiogeodrops): async, aiohttp + PyJWT only. |
| inject-websession | Done | The client uses `async_get_clientsession(hass)`. |
| strict-typing | **Partial** | `aiogeodrops` ships `py.typed` and passes `mypy --strict`; the integration itself is not yet annotated and has no mypy CI job. |

All three rules point at the same refactor: replace
`google-cloud-bigquery` with a small async library.

### Why the current dependency cannot get there

- No async variant exists, and it cannot take an `aiohttp` session.
- It pulls in `google-api-core[grpc]` → `grpcio`, `grpcio-status`,
  `protobuf`, plus `google-auth[pyopenssl]`, `google-resumable-media` and
  `requests`: a large native-code tree for one REST call per poll.

### The refactor: extract an `aiogeodrops` library

Core requires all device/service communication to live in a PyPI library,
and the three Platinum rules are judged on that library.

1. **New repo and PyPI package** (for example `aiogeodrops`), MIT or
   Apache-2.0, published from GitHub Actions (keeps `dependency-transparency`).
   Ships `py.typed`, passes `mypy --strict`.
2. **Dependencies: `aiohttp` and `PyJWT[crypto]` only.** Both already ship
   with Home Assistant core, so installation adds nothing native.
3. **Scope**, moved out of this repo:
   - Service-account auth: sign a JWT with the key's `private_key`, exchange it
     at `oauth2.googleapis.com/token`, cache the token until shortly before
     `expires_in`. Map `invalid_grant` to `GeoDropsAuthError`, token-endpoint
     5xx/429 to `GeoDropsConnectionError` (today's `_is_auth_error` logic).
   - Query: `POST bigquery/v2/projects/{project}/queries` with `timeoutMs`,
     `useLegacySql: false` and named parameters; if `jobComplete` is false,
     poll `getQueryResults` until an overall deadline (today's 60 s bound).
     Map 401 → auth error, 403 → access-denied error, others → query error.
   - Row parsing: BigQuery REST returns `INT64` as strings and `TIMESTAMP` as
     epoch-second strings. Parse against the response `schema` into the
     `DeviceReading` dataclass (today's `transform.reading_from_row`).
   - Public API:
     `GeoDropsClient(session, project_id, credentials_json)` with
     `async validate_access()`, `async fetch_latest(device_ids, lookback_hours)`
     and `async lookup_serial(serial, lookback_hours)`.
   - Tests with `aioresponses`; 100 % coverage.
4. **Alternative:** build on `gcloud-aio-bigquery` (`Job.query()` takes an
   aiohttp-backed `session` and a `service_file` stream). Less code to own,
   but it adds `gcloud-aio-auth` and its dependencies. Prefer the direct
   approach above.

### Integration changes after the library exists

- `manifest.json`: `"requirements": ["aiogeodrops==X.Y.Z"]`, add
  `"loggers": ["aiogeodrops"]`.
- `__init__.py`: `GeoDropsClient(async_get_clientsession(hass), ...)`. No
  executor jobs, no `client.close()` (HA owns the session).
- `config_flow.py`: `_validate_credentials` and `_lookup_device_id` become
  plain awaits.
- Delete `bigquery_api.py`; keep only staleness logic in `transform.py`.
- Stop test-patching module functions; mock `GeoDropsClient` with a
  `mock_geodrops_client` fixture in `conftest.py` (core pattern).

### Strict typing (in this repo, alongside the library)

- Type every function. Use `DataUpdateCoordinator[dict[int, DeviceReading]]`,
  `GeoDropsConfigEntry` in all signatures, `ConfigFlowResult` for flow steps,
  `AddConfigEntryEntitiesCallback` in `sensor.async_setup_entry`, and a
  `TypedDict` for the per-probe option dict.
- Use `self.config_entry` in the coordinator and drop the duplicate
  `self.entry`.
- Add a `mypy` CI job with HA's strict settings (`disallow_untyped_defs`,
  `disallow_any_generics`, `warn_return_any`, `no_implicit_optional`, …)
  over `custom_components/geodrops`.

---

## Development-guidelines conformance

Not quality-scale rules, but a core reviewer blocks on them. A ruff pass with
HA-style rule families (`D`, `UP`, `I`, `E`, `SIM`, `TRY`, `PL`) finds 81
issues, 30 auto-fixable:

| Count | Issue |
| --- | --- |
| 36 | Missing docstrings (`D101`–`D107`) |
| 22 | `Optional[X]` / quoted annotations instead of `X \| None` (`UP045`, `UP037`) |
| 7 | Imports inside functions (`PLC0415`): the lazy google imports; gone after the library refactor |
| 6 | Unsorted imports, and `from .transform import …` below code in `bigquery_api.py` (`I001`, `E402`) |
| 10 | Assorted: `typing.Callable`, `timezone.utc`, `TRY003/301/004`, `SIM103`, `RUF046` |

Also from the guidelines:

- Comments must be full sentences ending in a period (many are lowercase
  fragments, e.g. `# entry.data keys`).
- Log messages should not name the integration ("GeoDrops probe %s …"); the
  logger name already does.
- Constants should be alphabetical within groups (`const.py`).
- Add `ruff check` and `ruff format --check` to CI with HA core's
  `pyproject.toml` ruff settings.

## Core parity notes

- **Configurable poll interval.** Core reviewers do not accept a
  scan-interval option; users are pointed to disabling polling and calling
  `homeassistant.update_entity` from an automation. Fine for HACS; drop
  `scan_interval_minutes` only if core submission becomes a goal.
- **`quality_scale.yaml`.** Core tracks rule status in this file next to
  `manifest.json`. Adding one here keeps this document's status table in
  the repo in machine-readable form. Run hassfest locally first to confirm it
  accepts the file for a custom integration.

## Suggested order

| Release | Content | Estimate |
| --- | --- | --- |
| 0.6.x | Bronze + Silver fixes: field descriptions, recovery tests, removal docs, `PARALLEL_UPDATES`, options table | Done |
| 0.7.0 | Gold code: diagnostics, entity category/class/disabled-by-default, exception translations, repair issue, device-page removal | Done |
| 0.7.x | Gold docs: use cases, examples, limitations, supported devices, troubleshooting | Done |
| 0.8.0 | Ruff/docstring cleanup and full type annotations + mypy CI | 1 day |
| 1.0.0 | `aiogeodrops` library, then switch the integration to it | Done (`aiogeodrops` 0.1.0 on PyPI) |

The 1.0.0 step is the only risky one: it replaces the whole data path. Ship
it as a beta and compare readings against 0.8 on a live install before
promoting.

"""BigQuery access. Heavy google libs imported lazily so pure tests stay dep-free."""
from __future__ import annotations

from typing import Optional

from .const import BQ_TABLE

# Bound every query. The library defaults retry RPCs for up to 10 minutes and
# failed jobs for up to 40, with no overall wait limit: during a Google outage
# a single poll (or the setup / add-probe form) would hang that long. With
# these, a query gives up after ~60 s (worst case ~80 s with one HTTP call in
# flight) and the next poll tries again.
QUERY_TIMEOUT = 60
_API_TIMEOUT = 20   # per HTTP request
from .transform import DeviceReading, reading_from_row

_COLUMNS = """
      deviceId, mfgSn, date, moistureIndex, moisturePct,
      moisturePctDepth1, moisturePctDepth2, moisturePctDepth3,
      temperatureCSurface, temperatureCDepth1, temperatureCDepth2, temperatureCDepth3,
      miscSensorSyncDelayHour, miscBattPercent, avg7dSunExposureHourPerDay,
      qcnDepth1, qcnDepth2, qcnDepth3""".rstrip()


class CredentialsError(Exception):
    """Service-account JSON is malformed or unusable."""


class QueryError(Exception):
    """BigQuery rejected the query (permission, project, network)."""


class AuthError(QueryError):
    """Google rejected the service-account key itself (revoked, deleted, disabled).

    Only a new key fixes this, so callers surface it as a reauth. Permission
    errors (403) stay plain QueryError: they're fixed in IAM (or on GeoDrops'
    side), not by pasting a different key, and recover on retry once fixed.
    """


def _is_auth_error(err: BaseException) -> bool:
    try:
        from google.api_core.exceptions import Unauthorized
        from google.auth.exceptions import RefreshError
    except ImportError:
        return False
    while err is not None:
        if isinstance(err, Unauthorized):
            return True
        if isinstance(err, RefreshError):
            # google-auth marks token-endpoint outages (5xx, 429,
            # temporarily_unavailable) retryable; the key itself is fine then
            return not getattr(err, "retryable", False)
        err = err.__cause__
    return False


def _run(client, sql: str, job_config=None):
    from google.cloud.bigquery.retry import DEFAULT_JOB_RETRY, DEFAULT_RETRY

    try:
        return list(client.query_and_wait(
            sql, job_config=job_config,
            api_timeout=_API_TIMEOUT, wait_timeout=QUERY_TIMEOUT,
            retry=DEFAULT_RETRY.with_timeout(QUERY_TIMEOUT),
            job_retry=DEFAULT_JOB_RETRY.with_timeout(QUERY_TIMEOUT),
        ))
    except Exception as err:  # google.api_core / google.auth exceptions
        if _is_auth_error(err):
            raise AuthError(str(err)) from err
        raise QueryError(str(err)) from err


def build_latest_query(device_ids, lookback_hours: int) -> str:
    ids = ", ".join(str(int(d)) for d in device_ids)
    return (
        f"SELECT{_COLUMNS}\n"
        f"    FROM `{BQ_TABLE}`\n"
        f"    WHERE deviceId IN ({ids})\n"
        f"      AND createdAtOrigin > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), "
        f"INTERVAL {int(lookback_hours)} HOUR)\n"
        f"    QUALIFY ROW_NUMBER() OVER (PARTITION BY deviceId ORDER BY date DESC) = 1"
    )


def build_serial_lookup_query(lookback_hours: int) -> str:
    return (
        f"SELECT{_COLUMNS}\n"
        f"    FROM `{BQ_TABLE}`\n"
        f"    WHERE mfgSn = @serial\n"
        f"      AND createdAtOrigin > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), "
        f"INTERVAL {int(lookback_hours)} HOUR)\n"
        f"    ORDER BY date DESC\n"
        f"    LIMIT 1"
    )


def make_client(project_id: str, credentials_json: str):
    import json
    from google.cloud import bigquery
    from google.oauth2 import service_account

    try:
        info = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(info)
    except (ValueError, KeyError) as err:
        raise CredentialsError(str(err)) from err
    return bigquery.Client(credentials=creds, project=project_id)


def validate_access(client) -> None:
    """Trivial, near-zero-cost probe that confirms table read access.

    Selects a literal (no columns referenced) so BigQuery bills ~0 bytes,
    while still exercising real permission/auth/project checks against the
    table. Used to validate credentials during config flow setup, where an
    empty device-id list would otherwise force `WHERE deviceId IN ()` --
    invalid GoogleSQL that BigQuery rejects for every user, valid or not.
    """
    _run(client, f"SELECT 1 FROM `{BQ_TABLE}` LIMIT 1")


def fetch_latest(client, device_ids, lookback_hours: int):
    rows = _run(client, build_latest_query(device_ids, lookback_hours))
    return {r.deviceId: reading_from_row(r) for r in rows}


def _default_param_factory(serial: str):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("serial", "STRING", serial)]
    )


def lookup_serial(
    client, serial: str, lookback_hours: int, param_factory=_default_param_factory
) -> Optional[DeviceReading]:
    rows = _run(client, build_serial_lookup_query(lookback_hours),
                job_config=param_factory(serial))
    return reading_from_row(rows[0]) if rows else None

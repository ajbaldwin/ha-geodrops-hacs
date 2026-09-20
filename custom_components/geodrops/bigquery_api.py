"""BigQuery access. Heavy google libs imported lazily so pure tests stay dep-free."""
from __future__ import annotations

from typing import Optional

from .const import BQ_TABLE
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
    """BigQuery rejected the query (auth, permission, project)."""


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
    sql = f"SELECT 1 FROM `{BQ_TABLE}` LIMIT 1"
    try:
        list(client.query(sql))
    except Exception as err:  # google.api_core exceptions
        raise QueryError(str(err)) from err


def fetch_latest(client, device_ids, lookback_hours: int):
    sql = build_latest_query(device_ids, lookback_hours)
    try:
        rows = list(client.query(sql))
    except Exception as err:  # google.api_core exceptions
        raise QueryError(str(err)) from err
    return {r.deviceId: reading_from_row(r) for r in rows}


def _default_param_factory(serial: str):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("serial", "STRING", serial)]
    )


def lookup_serial(
    client, serial: str, lookback_hours: int, param_factory=_default_param_factory
) -> Optional[DeviceReading]:
    sql = build_serial_lookup_query(lookback_hours)
    try:
        rows = list(client.query(sql, job_config=param_factory(serial)))
    except Exception as err:
        raise QueryError(str(err)) from err
    return reading_from_row(rows[0]) if rows else None

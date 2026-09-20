import pytest
from custom_components.geodrops import bigquery_api as bq


class FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def query(self, sql, job_config=None):
        self.last_sql = sql
        self.last_params = job_config
        return self._rows


def test_build_latest_query_filters_ids_and_lookback():
    sql = bq.build_latest_query([1001, 1002], 12)
    assert "deviceId IN (1001, 1002)" in sql
    assert "INTERVAL 12 HOUR" in sql
    assert "ROW_NUMBER() OVER (PARTITION BY deviceId ORDER BY date DESC) = 1" in sql
    assert "geodrops-prod.db_public.p_sensor_unified" in sql


def test_build_serial_lookup_query_is_parameterized():
    sql = bq.build_serial_lookup_query(12)
    assert "mfgSn = @serial" in sql
    assert "LIMIT 1" in sql
    assert "INTERVAL 12 HOUR" in sql


def test_fetch_latest_maps_rows_by_device_id():
    rows = [FakeRow(deviceId=1001, moisturePct=42.0, qcnDepth1=2),
            FakeRow(deviceId=1002, moisturePct=10.0, qcnDepth1=1)]
    client = FakeClient(rows)
    out = bq.fetch_latest(client, [1001, 1002], 12)
    assert set(out) == {1001, 1002}
    assert out[1001].moisture_pct == 42.0


def test_lookup_serial_returns_reading_or_none():
    client = FakeClient([FakeRow(deviceId=1001, mfgSn="AAA111", moisturePct=42.0)])
    r = bq.lookup_serial(client, "AAA111", 12, param_factory=lambda s: None)
    assert r.device_id == 1001
    empty = FakeClient([])
    assert bq.lookup_serial(empty, "ZZZ999", 12, param_factory=lambda s: None) is None

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
        self.last_kwargs = None

    def query_and_wait(self, sql, job_config=None, **kwargs):
        self.last_sql = sql
        self.last_params = job_config
        self.last_kwargs = kwargs
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


def test_validate_access_succeeds_on_row():
    client = FakeClient([FakeRow(x=1)])
    bq.validate_access(client)   # no exception
    assert "SELECT 1" in client.last_sql
    assert "IN (" not in client.last_sql   # never builds an empty deviceId IN () clause


def test_validate_access_wraps_query_error():
    class RaisingClient:
        def query_and_wait(self, sql, job_config=None, **kwargs):
            raise RuntimeError("permission denied")

    with pytest.raises(bq.QueryError):
        bq.validate_access(RaisingClient())


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


def _raising_client(exc):
    class RaisingClient:
        def query_and_wait(self, sql, job_config=None, **kwargs):
            raise exc
    return RaisingClient()


@pytest.mark.parametrize("exc", [
    __import__("google.auth.exceptions", fromlist=["RefreshError"]).RefreshError(
        "invalid_grant: Invalid JWT Signature."),
    __import__("google.api_core.exceptions", fromlist=["Unauthorized"]).Unauthorized("401"),
])
def test_rejected_key_raises_auth_error(exc):
    with pytest.raises(bq.AuthError):
        bq.fetch_latest(_raising_client(exc), [1001], 12)


def test_auth_error_found_through_exception_cause():
    from google.auth.exceptions import RefreshError
    wrapper = RuntimeError("transport failed")
    wrapper.__cause__ = RefreshError("invalid_grant")
    with pytest.raises(bq.AuthError):
        bq.validate_access(_raising_client(wrapper))


def test_permission_denied_is_not_an_auth_error():
    # 403 is fixed in IAM (or on GeoDrops' side), not by a new key -> keep retrying
    from google.api_core.exceptions import Forbidden
    with pytest.raises(bq.QueryError) as info:
        bq.lookup_serial(_raising_client(Forbidden("Access Denied")), "AAA111", 12,
                         param_factory=lambda s: None)
    assert not isinstance(info.value, bq.AuthError)


def test_retryable_token_refresh_failure_is_not_an_auth_error():
    # Google's token endpoint having an outage must not trigger reauth: that
    # would stop polling until the user re-pastes a key that was never bad
    from google.auth.exceptions import RefreshError
    exc = RefreshError("temporarily_unavailable", retryable=True)
    with pytest.raises(bq.QueryError) as info:
        bq.fetch_latest(_raising_client(exc), [1001], 12)
    assert not isinstance(info.value, bq.AuthError)


def test_network_failure_is_not_an_auth_error():
    from google.auth.exceptions import TransportError
    from google.api_core.exceptions import ServiceUnavailable
    for exc in (TransportError("connection reset"), ServiceUnavailable("503")):
        with pytest.raises(bq.QueryError) as info:
            bq.fetch_latest(_raising_client(exc), [1001], 12)
        assert not isinstance(info.value, bq.AuthError)


def test_every_query_is_bounded_to_the_timeout():
    client = FakeClient([])
    bq.fetch_latest(client, [1001], 12)
    kw = client.last_kwargs
    assert kw["wait_timeout"] == bq.QUERY_TIMEOUT == 60
    assert kw["api_timeout"] <= bq.QUERY_TIMEOUT
    assert kw["retry"].timeout == bq.QUERY_TIMEOUT       # library default: 600 s
    assert kw["job_retry"].timeout == bq.QUERY_TIMEOUT   # library default: 2400 s

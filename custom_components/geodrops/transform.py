"""Pure transforms: value maps, row normalization, staleness classification."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Enum states are translation keys (see strings.json "entity" and icons.json):
# the UI shows "Good", "Wet+", ... while automations compare the stable keys.
# An unmapped value is None, i.e. Home Assistant's own "unknown".
_QCN_STATE = {2: "good", 1: "poor", 0: "bad", -1: "training"}
QCN_OPTIONS = ["bad", "poor", "good", "training"]

_MI_STATE = {5: "wet_plus", 4: "wet", 3: "moist_plus", 2: "moist", 1: "dry_plus", 0: "dry"}
MOISTURE_STATE_OPTIONS = ["dry", "dry_plus", "moist", "moist_plus", "wet", "wet_plus"]


def qcn_to_state(value) -> Optional[str]:
    return _QCN_STATE.get(value)


def moisture_index_to_state(value) -> Optional[str]:
    return _MI_STATE.get(value)


def classify_staleness(age_hours: float, warn_hours: int, skip_hours: int) -> str:
    """'skip' above skip_hours, 'warn' above warn_hours, else 'ok'. Strict > (matches source)."""
    if age_hours > skip_hours:
        return "skip"
    if age_hours > warn_hours:
        return "warn"
    return "ok"


def data_age_hours(reading: "DeviceReading", now: datetime) -> Optional[float]:
    """How old a reading is, in hours: the larger of GeoDrops' sync delay and
    the time since the reading's own timestamp.

    The sync delay is a number stored in the row, so while GeoDrops keeps
    serving the same row it stays frozen; the timestamp keeps aging with the
    clock. None when neither is known.
    """
    ages = [reading.sync_delay_hours]
    if reading.read_at is not None:
        ages.append((now - reading.read_at).total_seconds() / 3600)
    ages = [a for a in ages if a is not None]
    return max(ages) if ages else None


@dataclass(frozen=True)
class DeviceReading:
    # numeric fields are None when GeoDrops has no value (shown as unknown)
    device_id: int
    sync_delay_hours: Optional[float]
    moisture_index: int
    moisture_pct: Optional[float]
    moisture_d1: Optional[float]
    moisture_d2: Optional[float]
    moisture_d3: Optional[float]
    temp_surface: Optional[float]
    temp_d1: Optional[float]
    temp_d2: Optional[float]
    temp_d3: Optional[float]
    battery_pct: Optional[float]
    sun_7d: Optional[float]
    qcn_d1: int
    qcn_d2: int
    qcn_d3: int
    read_at: Optional[datetime] = None   # when the probe took the reading


def _num(row, attr):
    """Missing/None stays None (unknown); a real 0 is kept."""
    return getattr(row, attr, None)


def _qcn(row, attr):
    """QCN/index default is -1 (Training/Unknown) when missing or None."""
    value = getattr(row, attr, None)
    return -1 if value is None else value


def _timestamp(row, attr):
    """GeoDrops' `date` is a TIMESTAMP (tz-aware). A naive one is taken as UTC;
    anything else (e.g. a plain DATE after a schema change) is unknown."""
    value = getattr(row, attr, None)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reading_from_row(row) -> DeviceReading:
    return DeviceReading(
        device_id=row.deviceId,
        sync_delay_hours=_num(row, "miscSensorSyncDelayHour"),
        moisture_index=_qcn(row, "moistureIndex"),
        moisture_pct=_num(row, "moisturePct"),
        moisture_d1=_num(row, "moisturePctDepth1"),
        moisture_d2=_num(row, "moisturePctDepth2"),
        moisture_d3=_num(row, "moisturePctDepth3"),
        temp_surface=_num(row, "temperatureCSurface"),
        temp_d1=_num(row, "temperatureCDepth1"),
        temp_d2=_num(row, "temperatureCDepth2"),
        temp_d3=_num(row, "temperatureCDepth3"),
        battery_pct=_num(row, "miscBattPercent"),
        sun_7d=_num(row, "avg7dSunExposureHourPerDay"),
        qcn_d1=_qcn(row, "qcnDepth1"),
        qcn_d2=_qcn(row, "qcnDepth2"),
        qcn_d3=_qcn(row, "qcnDepth3"),
        read_at=_timestamp(row, "date"),
    )


def all_training(reading: DeviceReading) -> bool:
    return reading.qcn_d1 == -1 and reading.qcn_d2 == -1 and reading.qcn_d3 == -1

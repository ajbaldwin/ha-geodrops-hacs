"""Pure transforms: value maps, row normalization, staleness classification."""
from __future__ import annotations

from dataclasses import dataclass

_QCN_STATE = {2: "Good", 1: "Poor", 0: "Bad", -1: "Training"}
_QCN_ICON = {2: "mdi:check-circle", 1: "mdi:alert", 0: "mdi:close-circle", -1: "mdi:school"}
QCN_OPTIONS = ["Bad", "Poor", "Good", "Training", "Unknown"]

_MI_STATE = {5: "Wet+", 4: "Wet", 3: "Moist+", 2: "Moist", 1: "Dry+", 0: "Dry", -1: "Unknown"}
_MI_ICON = {
    5: "mdi:water", 4: "mdi:water-outline", 3: "mdi:water-percent",
    2: "mdi:water-percent-alert", 1: "mdi:water-alert-outline", 0: "mdi:water-off",
    -1: "mdi:help-circle",
}
MOISTURE_STATE_OPTIONS = ["Dry", "Dry+", "Moist", "Moist+", "Wet", "Wet+", "Unknown"]


def qcn_to_state(value) -> str:
    return _QCN_STATE.get(value, "Unknown")


def qcn_to_icon(value) -> str:
    return _QCN_ICON.get(value, "mdi:help-circle")


def moisture_index_to_state(value) -> str:
    return _MI_STATE.get(value, "Unknown")


def moisture_index_to_icon(value) -> str:
    return _MI_ICON.get(value, "mdi:help-circle")


def classify_staleness(sync_delay_hours: float, warn_hours: int, skip_hours: int) -> str:
    """'skip' above skip_hours, 'warn' above warn_hours, else 'ok'. Strict > (matches source)."""
    if sync_delay_hours > skip_hours:
        return "skip"
    if sync_delay_hours > warn_hours:
        return "warn"
    return "ok"


@dataclass(frozen=True)
class DeviceReading:
    device_id: int
    sync_delay_hours: float
    moisture_index: int
    moisture_pct: float
    moisture_d1: float
    moisture_d2: float
    moisture_d3: float
    temp_surface: float
    temp_d1: float
    temp_d2: float
    temp_d3: float
    battery_pct: float
    sun_7d: float
    qcn_d1: int
    qcn_d2: int
    qcn_d3: int


def _num(row, attr):
    """Source idiom `row.attr or 0`: missing/None/0 all collapse to 0."""
    return getattr(row, attr, None) or 0


def _qcn(row, attr):
    """QCN/index default is -1 (Training/Unknown) when missing or None."""
    value = getattr(row, attr, None)
    return -1 if value is None else value


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
    )


def all_training(reading: DeviceReading) -> bool:
    return reading.qcn_d1 == -1 and reading.qcn_d2 == -1 and reading.qcn_d3 == -1

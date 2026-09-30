"""Pure transforms: state maps and staleness classification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from aiogeodrops import DeviceReading

type Staleness = Literal["ok", "warn", "skip"]

# How far a row's sync delay may exceed the reading's own age before it is
# treated as bad data. Normal rows exceed it by about an hour at most.
SYNC_DELAY_SLACK_HOURS = 3

# Enum states are translation keys (see strings.json "entity" and icons.json):
# the UI shows "Good", "Wet+", ... while automations compare the stable keys.
# An unmapped value is None, i.e. Home Assistant's own "unknown".
_QCN_STATE = {2: "good", 1: "poor", 0: "bad", -1: "training"}
QCN_OPTIONS = ["bad", "poor", "good", "training"]

_MI_STATE = {
    5: "wet_plus",
    4: "wet",
    3: "moist_plus",
    2: "moist",
    1: "dry_plus",
    0: "dry",
}
MOISTURE_STATE_OPTIONS = ["dry", "dry_plus", "moist", "moist_plus", "wet", "wet_plus"]


def qcn_to_state(value: int) -> str | None:
    """Return the Quality sensor state for a GeoDrops qcn value."""
    return _QCN_STATE.get(value)


def moisture_index_to_state(value: int) -> str | None:
    """Return the Moisture State sensor state for a GeoDrops moisture index."""
    return _MI_STATE.get(value)


def classify_staleness(age_hours: float, warn_hours: int, skip_hours: int) -> Staleness:
    """'skip' above skip_hours, 'warn' above warn_hours, else 'ok'. Strict > (matches source)."""
    if age_hours > skip_hours:
        return "skip"
    if age_hours > warn_hours:
        return "warn"
    return "ok"


def sync_delay_hours(reading: DeviceReading, now: datetime) -> float | None:
    """Return GeoDrops' sync delay, or None when it can't be right.

    A probe's readings reach GeoDrops when it syncs, so its last sync can't be
    much older than its latest reading. Rows normally carry up to about an
    hour more delay than their own age, so SYNC_DELAY_SLACK_HOURS allows for
    that. GeoDrops has served a delay of ~2053 h on rows an hour old, which
    would otherwise mark a probe that is still reporting unavailable.
    """
    delay = reading.sync_delay_hours
    if delay is None or reading.read_at is None:
        return delay
    clock_age = (now - reading.read_at).total_seconds() / 3600
    if delay > clock_age + SYNC_DELAY_SLACK_HOURS:
        return None
    return delay


def data_age_hours(reading: DeviceReading, now: datetime) -> float | None:
    """Return how old a reading is, in hours.

    That is the larger of GeoDrops' sync delay and the time since the
    reading's own timestamp. The sync delay is a number stored in the row, so while GeoDrops keeps
    serving the same row it stays frozen; the timestamp keeps aging with the
    clock. An implausible sync delay is ignored (see sync_delay_hours). None
    when neither is known.
    """
    ages: list[float] = []
    delay = sync_delay_hours(reading, now)
    if delay is not None:
        ages.append(delay)
    if reading.read_at is not None:
        ages.append((now - reading.read_at).total_seconds() / 3600)
    return max(ages, default=None)

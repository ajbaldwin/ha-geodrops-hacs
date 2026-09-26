"""GeoDrops sensor platform: 16 sensors per probe."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const
from .transform import (
    DeviceReading, all_training, classify_staleness, data_age_hours,
    qcn_to_state, moisture_index_to_state,
    QCN_OPTIONS, MOISTURE_STATE_OPTIONS,
)


@dataclass(frozen=True)
class SensorSpec:
    suffix: str            # unique-id suffix; never change (entities would be re-created)
    translation_key: str   # name (and enum state labels) in strings.json, icons in icons.json
    value: Callable[[DeviceReading], object]
    device_class: Optional[str] = None
    unit: Optional[str] = None
    state_class: Optional[str] = None
    options: Optional[list] = None
    placeholders: Optional[dict] = None   # fills {depth} etc. in the translated name
    moisture_gated: bool = False   # None when device is all-training


_PCT = dict(device_class=SensorDeviceClass.MOISTURE, unit="%", state_class=SensorStateClass.MEASUREMENT)
_TEMP = dict(device_class=SensorDeviceClass.TEMPERATURE, unit="°C", state_class=SensorStateClass.MEASUREMENT)
_QCN = dict(device_class=SensorDeviceClass.ENUM, options=QCN_OPTIONS)


def _depth(n):
    return {"depth": str(n)}


SENSOR_SPECS = [
    SensorSpec("moisture", "moisture", lambda r: r.moisture_pct, moisture_gated=True, **_PCT),
    SensorSpec("moisture_state", "moisture_state",
               lambda r: moisture_index_to_state(r.moisture_index),
               device_class=SensorDeviceClass.ENUM, options=MOISTURE_STATE_OPTIONS,
               moisture_gated=True),
    SensorSpec("moisture_d1", "moisture_depth", lambda r: r.moisture_d1, placeholders=_depth(1),
               moisture_gated=True, **_PCT),
    SensorSpec("moisture_d2", "moisture_depth", lambda r: r.moisture_d2, placeholders=_depth(2),
               moisture_gated=True, **_PCT),
    SensorSpec("moisture_d3", "moisture_depth", lambda r: r.moisture_d3, placeholders=_depth(3),
               moisture_gated=True, **_PCT),
    SensorSpec("qcn_d1", "qcn_depth", lambda r: qcn_to_state(r.qcn_d1), placeholders=_depth(1), **_QCN),
    SensorSpec("qcn_d2", "qcn_depth", lambda r: qcn_to_state(r.qcn_d2), placeholders=_depth(2), **_QCN),
    SensorSpec("qcn_d3", "qcn_depth", lambda r: qcn_to_state(r.qcn_d3), placeholders=_depth(3), **_QCN),
    SensorSpec("battery", "battery",
               lambda r: None if r.battery_pct is None else int(round(r.battery_pct)),
               device_class=SensorDeviceClass.BATTERY, unit="%", state_class=SensorStateClass.MEASUREMENT),
    SensorSpec("sync_delay", "sync_delay", lambda r: r.sync_delay_hours, unit="h",
               state_class=SensorStateClass.MEASUREMENT),
    SensorSpec("temp_surface", "surface_temperature", lambda r: r.temp_surface, **_TEMP),
    SensorSpec("temp_d1", "temperature_depth", lambda r: r.temp_d1, placeholders=_depth(1), **_TEMP),
    SensorSpec("temp_d2", "temperature_depth", lambda r: r.temp_d2, placeholders=_depth(2), **_TEMP),
    SensorSpec("temp_d3", "temperature_depth", lambda r: r.temp_d3, placeholders=_depth(3), **_TEMP),
    SensorSpec("sun_7d", "sun_7d", lambda r: r.sun_7d, unit="h",
               state_class=SensorStateClass.MEASUREMENT),
    SensorSpec("last_reading", "last_reading", lambda r: r.read_at,
               device_class=SensorDeviceClass.TIMESTAMP),
]


class GeoDropsSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device, spec):
        super().__init__(coordinator)
        self._device = device
        self._spec = spec
        self._suffix = spec.suffix
        serial = device[const.DEV_SERIAL]
        self._attr_unique_id = f"{serial}_{spec.suffix}"
        self._attr_translation_key = spec.translation_key
        if spec.placeholders:
            self._attr_translation_placeholders = spec.placeholders
        self._attr_device_class = spec.device_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_state_class = spec.state_class
        if spec.options:
            self._attr_options = spec.options
        device_info = DeviceInfo(
            identifiers={(const.DOMAIN, serial)},
            name=device[const.DEV_NAME],
            manufacturer="GeoDrops",
            model="GeoDrops Droplet",
            serial_number=serial,
        )
        area_id = device.get(const.DEV_AREA)
        if area_id:
            area = ar.async_get(coordinator.hass).async_get_area(area_id)
            if area is not None:
                device_info["suggested_area"] = area.name
        self._attr_device_info = device_info

    @property
    def _reading(self):
        return self.coordinator.reading(self._device[const.DEV_ID])

    @property
    def available(self):
        r = self._reading
        if r is None:
            return False
        skip = self.coordinator.entry.options.get(const.CONF_SKIP_HOURS, const.DEFAULT_SKIP_HOURS)
        warn = self.coordinator.entry.options.get(const.CONF_WARN_HOURS, const.DEFAULT_WARN_HOURS)
        age = data_age_hours(r, dt_util.utcnow())
        if age is not None and classify_staleness(age, warn, skip) == "skip":
            return False
        expire = self.coordinator.entry.options.get(
            const.CONF_EXPIRE_MINUTES, const.DEFAULT_EXPIRE_MINUTES)
        last = self.coordinator.reading_time(self._device[const.DEV_ID])
        if last is None or dt_util.utcnow() - last > timedelta(minutes=expire):
            return False
        return True

    @property
    def native_value(self):
        r = self._reading
        if r is None:
            return None
        if self._spec.moisture_gated and all_training(r):
            return None
        return self._spec.value(r)


def build_sensors(coordinator, device):
    return [GeoDropsSensor(coordinator, device, spec) for spec in SENSOR_SPECS]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = []
    for device in entry.options.get(const.CONF_DEVICES, []):
        entities.extend(build_sensors(coordinator, device))
    async_add_entities(entities)

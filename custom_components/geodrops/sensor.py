"""GeoDrops sensor platform: 15 sensors per probe."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const
from .transform import (
    DeviceReading, all_training, classify_staleness,
    qcn_to_state, qcn_to_icon, moisture_index_to_state, moisture_index_to_icon,
    QCN_OPTIONS, MOISTURE_STATE_OPTIONS,
)


@dataclass(frozen=True)
class SensorSpec:
    suffix: str
    name: str
    value: Callable[[DeviceReading], object]
    device_class: Optional[str] = None
    unit: Optional[str] = None
    state_class: Optional[str] = None
    options: Optional[list] = None
    icon: Optional[Callable[[DeviceReading], str]] = None
    moisture_gated: bool = False   # None when device is all-training


_PCT = dict(device_class=SensorDeviceClass.MOISTURE, unit="%", state_class=SensorStateClass.MEASUREMENT)
_TEMP = dict(device_class=SensorDeviceClass.TEMPERATURE, unit="°C", state_class=SensorStateClass.MEASUREMENT)

SENSOR_SPECS = [
    SensorSpec("moisture", "Dominant Moisture", lambda r: r.moisture_pct, moisture_gated=True, **_PCT),
    SensorSpec("moisture_state", "Moisture State", lambda r: moisture_index_to_state(r.moisture_index),
               device_class=SensorDeviceClass.ENUM, options=MOISTURE_STATE_OPTIONS,
               icon=lambda r: moisture_index_to_icon(r.moisture_index), moisture_gated=True),
    SensorSpec("moisture_d1", "Moisture Depth 1", lambda r: r.moisture_d1, moisture_gated=True, **_PCT),
    SensorSpec("moisture_d2", "Moisture Depth 2", lambda r: r.moisture_d2, moisture_gated=True, **_PCT),
    SensorSpec("moisture_d3", "Moisture Depth 3", lambda r: r.moisture_d3, moisture_gated=True, **_PCT),
    SensorSpec("qcn_d1", "Quality Depth 1", lambda r: qcn_to_state(r.qcn_d1),
               device_class=SensorDeviceClass.ENUM, options=QCN_OPTIONS, icon=lambda r: qcn_to_icon(r.qcn_d1)),
    SensorSpec("qcn_d2", "Quality Depth 2", lambda r: qcn_to_state(r.qcn_d2),
               device_class=SensorDeviceClass.ENUM, options=QCN_OPTIONS, icon=lambda r: qcn_to_icon(r.qcn_d2)),
    SensorSpec("qcn_d3", "Quality Depth 3", lambda r: qcn_to_state(r.qcn_d3),
               device_class=SensorDeviceClass.ENUM, options=QCN_OPTIONS, icon=lambda r: qcn_to_icon(r.qcn_d3)),
    SensorSpec("battery", "Battery", lambda r: int(round(r.battery_pct)),
               device_class=SensorDeviceClass.BATTERY, unit="%", state_class=SensorStateClass.MEASUREMENT),
    SensorSpec("sync_delay", "Sync Delay", lambda r: r.sync_delay_hours, unit="h",
               state_class=SensorStateClass.MEASUREMENT),
    SensorSpec("temp_surface", "Surface Temperature", lambda r: r.temp_surface, **_TEMP),
    SensorSpec("temp_d1", "Temperature Depth 1", lambda r: r.temp_d1, **_TEMP),
    SensorSpec("temp_d2", "Temperature Depth 2", lambda r: r.temp_d2, **_TEMP),
    SensorSpec("temp_d3", "Temperature Depth 3", lambda r: r.temp_d3, **_TEMP),
    SensorSpec("sun_7d", "Avg. 7-Day Sun", lambda r: r.sun_7d, unit="h",
               state_class=SensorStateClass.MEASUREMENT, icon=lambda r: "mdi:white-balance-sunny"),
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
        self._attr_name = spec.name
        self._attr_device_class = spec.device_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_state_class = spec.state_class
        if spec.options:
            self._attr_options = spec.options
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, serial)},
            name=f"{device[const.DEV_NAME]} Moisture Sensor",
            manufacturer="GeoDrops",
            model="Soil Moisture Sensor",
            sw_version="vA2.03.r3",
        )

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
        if classify_staleness(r.sync_delay_hours, warn, skip) == "skip":
            return False
        expire = self.coordinator.entry.options.get(
            const.CONF_EXPIRE_MINUTES, const.DEFAULT_EXPIRE_MINUTES)
        last = self.coordinator.last_success_time
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

    @property
    def icon(self):
        r = self._reading
        if self._spec.icon and r is not None:
            return self._spec.icon(r)
        return None


def build_sensors(coordinator, device):
    return [GeoDropsSensor(coordinator, device, spec) for spec in SENSOR_SPECS]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    entities = []
    for device in entry.options.get(const.CONF_DEVICES, []):
        entities.extend(build_sensors(coordinator, device))
    async_add_entities(entities)

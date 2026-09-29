"""GeoDrops sensors: 16 per probe."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogeodrops import DeviceReading

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const
from .const import DeviceConfig
from .coordinator import GeoDropsConfigEntry, GeoDropsCoordinator
from .transform import (
    MOISTURE_STATE_OPTIONS,
    QCN_OPTIONS,
    classify_staleness,
    data_age_hours,
    moisture_index_to_state,
    qcn_to_state,
)

# The coordinator does all fetching, so entity updates need no limit.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GeoDropsSensorEntityDescription(SensorEntityDescription):
    """A GeoDrops sensor.

    `key` is the unique-id suffix: never change it (entities would be
    re-created). `translation_key` names the sensor (and its enum state labels)
    in strings.json and its icons in icons.json.
    """

    value_fn: Callable[[DeviceReading], StateType | datetime]
    # Report None while every depth is still training.
    moisture_gated: bool = False


def _moisture(
    key: str,
    value_fn: Callable[[DeviceReading], float | None],
    depth: int | None = None,
) -> GeoDropsSensorEntityDescription:
    """Describe a moisture sensor: overall, or at one depth."""
    return GeoDropsSensorEntityDescription(
        key=key,
        translation_key="moisture" if depth is None else "moisture_depth",
        translation_placeholders=None if depth is None else {"depth": str(depth)},
        value_fn=value_fn,
        moisture_gated=True,
        device_class=SensorDeviceClass.MOISTURE,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    )


def _temperature(
    key: str,
    value_fn: Callable[[DeviceReading], float | None],
    depth: int | None = None,
) -> GeoDropsSensorEntityDescription:
    """Describe a temperature sensor: at the surface, or at one depth."""
    return GeoDropsSensorEntityDescription(
        key=key,
        translation_key="surface_temperature" if depth is None else "temperature_depth",
        translation_placeholders=None if depth is None else {"depth": str(depth)},
        value_fn=value_fn,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    )


def _quality(
    key: str, value_fn: Callable[[DeviceReading], int], depth: int
) -> GeoDropsSensorEntityDescription:
    """Describe a per-depth reading-quality sensor."""
    # Per-depth reading quality: diagnostic, but enabled by default because
    # other integrations (e.g. irrigation schedulers) read these states to
    # decide whether a probe's moisture reading can be trusted. A disabled
    # entity has no state at all, which they would treat as an untrustworthy
    # probe.
    return GeoDropsSensorEntityDescription(
        key=key,
        translation_key="qcn_depth",
        translation_placeholders={"depth": str(depth)},
        value_fn=lambda r: qcn_to_state(value_fn(r)),
        device_class=SensorDeviceClass.ENUM,
        options=QCN_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


SENSOR_DESCRIPTIONS: tuple[GeoDropsSensorEntityDescription, ...] = (
    _moisture("moisture", lambda r: r.moisture_pct),
    GeoDropsSensorEntityDescription(
        key="moisture_state",
        translation_key="moisture_state",
        value_fn=lambda r: moisture_index_to_state(r.moisture_index),
        moisture_gated=True,
        device_class=SensorDeviceClass.ENUM,
        options=MOISTURE_STATE_OPTIONS,
    ),
    _moisture("moisture_d1", lambda r: r.moisture_d1, depth=1),
    _moisture("moisture_d2", lambda r: r.moisture_d2, depth=2),
    _moisture("moisture_d3", lambda r: r.moisture_d3, depth=3),
    _quality("qcn_d1", lambda r: r.qcn_d1, depth=1),
    _quality("qcn_d2", lambda r: r.qcn_d2, depth=2),
    _quality("qcn_d3", lambda r: r.qcn_d3, depth=3),
    GeoDropsSensorEntityDescription(
        key="battery",
        translation_key="battery",
        value_fn=lambda r: None if r.battery_pct is None else round(r.battery_pct),
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GeoDropsSensorEntityDescription(
        key="sync_delay",
        translation_key="sync_delay",
        value_fn=lambda r: r.sync_delay_hours,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Only applies when a probe is first added.
        entity_registry_enabled_default=False,
    ),
    _temperature("temp_surface", lambda r: r.temp_surface),
    _temperature("temp_d1", lambda r: r.temp_d1, depth=1),
    _temperature("temp_d2", lambda r: r.temp_d2, depth=2),
    _temperature("temp_d3", lambda r: r.temp_d3, depth=3),
    # Hours of sun per day is a rate, so it has no duration device class.
    GeoDropsSensorEntityDescription(
        key="sun_7d",
        translation_key="sun_7d",
        value_fn=lambda r: r.sun_7d,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    GeoDropsSensorEntityDescription(
        key="last_reading",
        translation_key="last_reading",
        value_fn=lambda r: r.read_at,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class GeoDropsSensor(CoordinatorEntity[GeoDropsCoordinator], SensorEntity):
    """One value from a probe's latest reading."""

    _attr_has_entity_name = True
    entity_description: GeoDropsSensorEntityDescription

    def __init__(
        self,
        coordinator: GeoDropsCoordinator,
        device: DeviceConfig,
        description: GeoDropsSensorEntityDescription,
    ) -> None:
        """Create the sensor for `description` on `device`'s probe."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device = device
        serial = device[const.DEV_SERIAL]
        self._attr_unique_id = f"{serial}_{description.key}"
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
    def _reading(self) -> DeviceReading | None:
        """The probe's latest reading."""
        return self.coordinator.reading(self._device[const.DEV_ID])

    @property
    def available(self) -> bool:
        """Return False when the probe's data is missing, too old or expired."""
        r = self._reading
        if r is None:
            return False
        options = self.coordinator.config_entry.options
        skip: int = options.get(const.CONF_SKIP_HOURS, const.DEFAULT_SKIP_HOURS)
        warn: int = options.get(const.CONF_WARN_HOURS, const.DEFAULT_WARN_HOURS)
        age = data_age_hours(r, dt_util.utcnow())
        if age is not None and classify_staleness(age, warn, skip) == "skip":
            return False
        expire: int = options.get(
            const.CONF_EXPIRE_MINUTES, const.DEFAULT_EXPIRE_MINUTES
        )
        last = self.coordinator.reading_time(self._device[const.DEV_ID])
        if last is None or dt_util.utcnow() - last > timedelta(minutes=expire):
            return False
        return True

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor's value from the latest reading."""
        r = self._reading
        if r is None:
            return None
        if self.entity_description.moisture_gated and r.all_training:
            return None
        return self.entity_description.value_fn(r)


def build_sensors(
    coordinator: GeoDropsCoordinator, device: DeviceConfig
) -> list[GeoDropsSensor]:
    """Create every sensor for one probe."""
    return [GeoDropsSensor(coordinator, device, desc) for desc in SENSOR_DESCRIPTIONS]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoDropsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors for every configured probe."""
    coordinator = entry.runtime_data
    entities: list[GeoDropsSensor] = []
    for device in coordinator.devices:
        entities.extend(build_sensors(coordinator, device))
    async_add_entities(entities)

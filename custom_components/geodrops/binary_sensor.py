"""GeoDrops binary sensors: 4 per probe."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aiogeodrops import DeviceReading

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DeviceConfig
from .coordinator import GeoDropsConfigEntry, GeoDropsCoordinator
from .entity import GeoDropsEntity
from .transform import (
    ERROR_CODES,
    HARDWARE_CODES,
    MAX_MOISTURE_CODES,
    RECALIBRATION_CODES,
    has_code,
)

# The coordinator does all fetching, so entity updates need no limit.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GeoDropsBinarySensorEntityDescription(BinarySensorEntityDescription):
    """A GeoDrops binary sensor.

    `key` is the unique-id suffix: never change it (entities would be
    re-created). `translation_key` names it in strings.json.
    """

    value_fn: Callable[[DeviceReading], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[GeoDropsBinarySensorEntityDescription, ...] = (
    GeoDropsBinarySensorEntityDescription(
        key="battery_poor",
        translation_key="battery_status",
        value_fn=lambda r: r.battery_poor,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Only applies when a probe is first added.
        entity_registry_enabled_default=False,
    ),
    # From GeoDrops' nextAction codes; see transform.py.
    GeoDropsBinarySensorEntityDescription(
        key="max_moisture_required",
        translation_key="max_moisture_required",
        value_fn=lambda r: has_code(r.next_action, MAX_MOISTURE_CODES),
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GeoDropsBinarySensorEntityDescription(
        # The key predates knowing what DW_RENEW means; it keeps the unique id.
        key="wick_renewal",
        translation_key="max_moisture_recalibration",
        value_fn=lambda r: has_code(r.next_action, RECALIBRATION_CODES),
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Only applies when a probe is first added; Probe Health covers it.
        entity_registry_enabled_default=False,
    ),
    GeoDropsBinarySensorEntityDescription(
        key="hardware_problem",
        translation_key="hardware_problem",
        value_fn=lambda r: has_code(r.next_action, HARDWARE_CODES | ERROR_CODES),
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Only applies when a probe is first added; Probe Health covers it.
        entity_registry_enabled_default=False,
    ),
)


class GeoDropsBinarySensor(GeoDropsEntity, BinarySensorEntity):
    """One flag from a probe's latest reading."""

    entity_description: GeoDropsBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the flag from the latest reading."""
        r = self._reading
        return None if r is None else self.entity_description.value_fn(r)


def build_binary_sensors(
    coordinator: GeoDropsCoordinator, device: DeviceConfig
) -> list[GeoDropsBinarySensor]:
    """Create every binary sensor for one probe."""
    return [
        GeoDropsBinarySensor(coordinator, device, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoDropsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors for every configured probe."""
    coordinator = entry.runtime_data
    entities: list[GeoDropsBinarySensor] = []
    for device in coordinator.devices:
        entities.extend(build_binary_sensors(coordinator, device))
    async_add_entities(entities)

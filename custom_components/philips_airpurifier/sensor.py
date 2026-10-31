"""Sensors for Philips air purifiers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    PHILIPS_ALLERGEN_INDEX,
    PHILIPS_HUMIDITY,
    PHILIPS_PM25,
    PHILIPS_TEMPERATURE,
    PHILIPS_WATER_LEVEL,
)
from .coordinator import PhilipsConfigEntry, PhilipsCoordinator, PhilipsData
from .entity import PhilipsEntity


@dataclass(frozen=True, kw_only=True)
class PhilipsSensorDescription(SensorEntityDescription):
    """Describes a value read from the status or filter endpoint."""

    source: Callable[[PhilipsData], dict[str, Any]]


def _status(data: PhilipsData) -> dict[str, Any]:
    return data.status


def _filters(data: PhilipsData) -> dict[str, Any]:
    return data.filters


SENSORS: tuple[PhilipsSensorDescription, ...] = (
    PhilipsSensorDescription(
        key=PHILIPS_PM25,
        source=_status,
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PhilipsSensorDescription(
        key=PHILIPS_ALLERGEN_INDEX,
        translation_key="allergen_index",
        source=_status,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PhilipsSensorDescription(
        key=PHILIPS_TEMPERATURE,
        source=_status,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PhilipsSensorDescription(
        key=PHILIPS_HUMIDITY,
        source=_status,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PhilipsSensorDescription(
        key=PHILIPS_WATER_LEVEL,
        translation_key="water_level",
        source=_status,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    *(
        PhilipsSensorDescription(
            key=key,
            translation_key=translation_key,
            source=_filters,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.HOURS,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        for key, translation_key in (
            ("fltsts0", "pre_filter"),
            ("fltsts1", "hepa_filter"),
            ("fltsts2", "carbon_filter"),
            ("wicksts", "wick_filter"),
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhilipsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a sensor for every value the device reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        PhilipsSensor(coordinator, description)
        for description in SENSORS
        if description.key in description.source(coordinator.data)
    )


class PhilipsSensor(PhilipsEntity, SensorEntity):
    """A single measured value."""

    entity_description: PhilipsSensorDescription

    def __init__(
        self, coordinator: PhilipsCoordinator, description: PhilipsSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._mac}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.source(self.coordinator.data).get(
            self.entity_description.key
        )

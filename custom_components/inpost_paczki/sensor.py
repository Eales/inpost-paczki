"""Sensor platform for InPost Paczki."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InPostConfigEntry
from .coordinator import InPostCoordinator
from .entity import InPostEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InPostConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up InPost sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            InPostReadyCountSensor(coordinator),
            InPostOnTheWayCountSensor(coordinator),
            InPostPickupDeadlineSensor(coordinator),
        ]
    )


class InPostReadyCountSensor(InPostEntity, SensorEntity):
    """How many parcels wait to be collected; the list is in ``parcels``."""

    _attr_translation_key = "ready"
    _attr_icon = "mdi:package-variant-closed-check"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "ready")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["ready"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"parcels": [self.parcel_attributes(p) for p in self.coordinator.data["ready"]]}


class InPostOnTheWayCountSensor(InPostEntity, SensorEntity):
    """How many parcels are announced or travelling; the list is in ``parcels``."""

    _attr_translation_key = "on_the_way"
    _attr_icon = "mdi:truck-delivery-outline"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "on_the_way")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["on_the_way"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "parcels": [self.parcel_attributes(p) for p in self.coordinator.data["on_the_way"]]
        }


class InPostPickupDeadlineSensor(InPostEntity, SensorEntity):
    """Earliest pickup deadline among parcels waiting in a locker or a point."""

    _attr_translation_key = "pickup_deadline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "pickup_deadline")

    @property
    def _parcel(self) -> dict[str, Any] | None:
        ready = [p for p in self.coordinator.data["ready"] if p["expiry_date"]]
        return ready[0] if ready else None

    @property
    def native_value(self) -> datetime | None:
        parcel = self._parcel
        return parcel["expiry_date"] if parcel else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        parcel = self._parcel
        return self.parcel_attributes(parcel) if parcel else {}

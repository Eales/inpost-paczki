"""Binary sensor platform for InPost Paczki."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up the InPost binary sensor from a config entry."""
    async_add_entities([InPostParcelWaitingSensor(entry.runtime_data)])


class InPostParcelWaitingSensor(InPostEntity, BinarySensorEntity):
    """On while at least one parcel waits to be collected."""

    _attr_translation_key = "parcel_waiting"
    _attr_icon = "mdi:package-variant-closed"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "parcel_waiting")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["ready"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ready = self.coordinator.data["ready"]
        return self.parcel_attributes(ready[0]) if ready else {}

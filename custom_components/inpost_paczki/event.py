"""Event platform for InPost Paczki."""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import InPostConfigEntry
from .coordinator import InPostCoordinator
from .entity import InPostEntity

EVENT_NEW_PARCEL = "new_parcel"
EVENT_STATUS_CHANGED = "status_changed"
EVENT_READY_TO_PICKUP = "ready_to_pickup"
EVENT_DELIVERED = "delivered"
EVENT_NOTIFICATION = "notification"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InPostConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the InPost event entities."""
    coordinator = entry.runtime_data
    async_add_entities([InPostParcelEvent(coordinator), InPostNotificationEvent(coordinator)])


class InPostEventEntity(InPostEntity, EventEntity):
    """Announces what a refresh found, exactly once per refresh.

    The first refresh after start-up runs before the entity exists, and it is
    the one that sees what happened while Home Assistant was down - so pending
    events are also flushed right after the entity is added.
    """

    def _events(self) -> list[tuple[str, dict[str, Any]]]:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Deferred: state can only be written once the entity is fully added.
        self.hass.loop.call_soon(self._announce)

    @callback
    def _announce(self) -> None:
        data = self.coordinator.data
        if not data or self.hass is None:
            return
        if self.coordinator.announced.get(self.unique_id) == data["refresh_id"]:
            return
        self.coordinator.announced[self.unique_id] = data["refresh_id"]
        for event_type, attributes in self._events():
            self._trigger_event(event_type, attributes)
            # One state write per event, or several events in a refresh collapse.
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._announce()
        super()._handle_coordinator_update()


class InPostParcelEvent(InPostEventEntity):
    """Fires when a parcel appears or its status changes."""

    _attr_translation_key = "parcel"
    _attr_event_types = [
        EVENT_NEW_PARCEL,
        EVENT_STATUS_CHANGED,
        EVENT_READY_TO_PICKUP,
        EVENT_DELIVERED,
    ]
    _attr_icon = "mdi:package-variant"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "parcel_event")

    def _events(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (event_type, self.parcel_attributes(parcel))
            for event_type, parcel in self.coordinator.data["changes"]
        ]


class InPostNotificationEvent(InPostEventEntity):
    """Mirrors the notifications the InPost app shows, text included."""

    _attr_translation_key = "notification"
    _attr_event_types = [EVENT_NOTIFICATION]
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "notification_event")

    def _events(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (
                EVENT_NOTIFICATION,
                {
                    "title": n["title"],
                    "message": n["content"],
                    "shipment_number": n["shipment_number"],
                    "sender": n["sender"],
                    "date": dt_util.as_local(n["date"]).isoformat() if n["date"] else None,
                },
            )
            for n in self.coordinator.data["new_notifications"]
        ]

"""Calendar platform for InPost Paczki."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import InPostConfigEntry
from .coordinator import InPostCoordinator
from .entity import InPostEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InPostConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the InPost pickup calendar."""
    async_add_entities([InPostPickupCalendar(entry.runtime_data)])


def _to_event(parcel: dict[str, Any]) -> CalendarEvent | None:
    """A pickup window: from arrival in the locker until the deadline."""
    end = parcel["expiry_date"]
    if not end:
        return None
    start = parcel["stored_date"] or end - timedelta(hours=1)
    sender = parcel["sender"] or "nieznany nadawca"
    description = "\n".join(
        line
        for line in (
            f"Nadawca: {sender}",
            f"Przesyłka: {parcel['shipment_number']}",
            parcel["point_description"],
        )
        if line
    )
    return CalendarEvent(
        start=dt_util.as_local(start),
        end=dt_util.as_local(end),
        summary=f"Odbierz paczkę: {sender}",
        description=description,
        location=", ".join(p for p in (parcel["point_name"], parcel["point_address"]) if p),
        uid=parcel["shipment_number"],
    )


class InPostPickupCalendar(InPostEntity, CalendarEntity):
    """Pickup windows as events, so a calendar trigger can warn before the deadline."""

    _attr_translation_key = "pickups"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: InPostCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _events(self) -> list[CalendarEvent]:
        events = [_to_event(p) for p in self.coordinator.data["ready"]]
        return sorted((e for e in events if e is not None), key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        """The pickup window ending soonest that has not ended yet."""
        now = dt_util.now()
        upcoming = [e for e in self._events() if e.end > now]
        return min(upcoming, key=lambda e: e.end) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Pickup windows overlapping the requested range."""
        return [e for e in self._events() if e.start < end_date and e.end > start_date]

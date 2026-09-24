"""Shared entity base for InPost Paczki."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_SHOW_CODES, DEFAULT_SHOW_CODES, DOMAIN
from .coordinator import InPostCoordinator


class InPostEntity(CoordinatorEntity[InPostCoordinator]):
    """Base entity tying all entities of one account to a single device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: InPostCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="InPost",
            model="Paczki",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://inpost.pl/sledzenie-przesylek",
        )

    @property
    def show_codes(self) -> bool:
        return self.coordinator.entry.options.get(CONF_SHOW_CODES, DEFAULT_SHOW_CODES)

    def parcel_attributes(self, parcel: dict[str, Any]) -> dict[str, Any]:
        """Flat, template-free description of a parcel."""
        attributes: dict[str, Any] = {
            "shipment_number": parcel["shipment_number"],
            "sender": parcel["sender"],
            "status": parcel["state"],
            "status_title": parcel["status_title"],
            "point_name": parcel["point_name"],
            "point_address": parcel["point_address"],
            "point_description": parcel["point_description"],
            "expiry_date": _iso(parcel["expiry_date"]),
            "tracking_url": (
                f"https://inpost.pl/sledzenie-przesylek?number={parcel['shipment_number']}"
            ),
        }
        if self.show_codes:
            attributes["open_code"] = parcel["open_code"]
        return attributes


def _iso(value) -> str | None:
    return dt_util.as_local(value).isoformat() if value else None

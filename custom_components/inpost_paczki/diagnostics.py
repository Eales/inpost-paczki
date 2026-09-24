"""Diagnostics support for InPost Paczki."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import InPostConfigEntry
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_UID,
    CONF_PERSON_ID,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
)

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_DEVICE_UID,
    CONF_PERSON_ID,
    CONF_PHONE,
    "open_code",
    "qr_code",
    "latitude",
    "longitude",
    "sender",
    "shipment_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: InPostConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}

    def _plain(parcel: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in parcel.items()
        }

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "version": entry.version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
        "parcels": async_redact_data(
            [_plain(p) for p in data.get("parcels", [])], TO_REDACT
        ),
        "notification_count": len(data.get("notifications", [])),
    }

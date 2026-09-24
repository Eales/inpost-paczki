"""Parcel payload parsing and change detection.

Kept free of Home Assistant imports so it can be unit-tested on its own.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

# Our own coarse state of a parcel, derived from InPost's detailed status.
STATE_CREATED = "created"
STATE_IN_TRANSIT = "in_transit"
STATE_OUT_FOR_DELIVERY = "out_for_delivery"
STATE_READY = "ready_to_pickup"
STATE_DELIVERED = "delivered"
STATE_RETURNED = "returned"
STATE_OTHER = "other"

STATES = [
    STATE_CREATED,
    STATE_IN_TRANSIT,
    STATE_OUT_FOR_DELIVERY,
    STATE_READY,
    STATE_DELIVERED,
    STATE_RETURNED,
    STATE_OTHER,
]

_CREATED = {"CREATED", "CONFIRMED", "OFFERS_PREPARED", "OFFER_SELECTED"}
_OUT_FOR_DELIVERY = {"OUT_FOR_DELIVERY", "OUT_FOR_DELIVERY_TO_ADDRESS"}
_READY = {
    "READY_TO_PICKUP",
    "PICKUP_REMINDER_SENT",
    "READY_TO_PICKUP_FROM_POK",
    "READY_TO_PICKUP_FROM_POK_REGISTERED",
    "READY_TO_PICKUP_FROM_BRANCH",
    "STACK_IN_BOX_MACHINE",
    "STACK_IN_CUSTOMER_SERVICE_POINT",
    "AVIZO",
}
_DELIVERED = {"DELIVERED", "COLLECTED_BY_CUSTOMER"}
_RETURNED = {
    "RETURNED_TO_SENDER",
    "PICKUP_TIME_EXPIRED",
    "STACK_PARCEL_PICKUP_TIME_EXPIRED",
    "UNDELIVERED",
    "CANCELED",
    "REJECTED_BY_RECEIVER",
}
_OTHER = {"CLAIMED", "MISSING", "OVERSIZED", "NOT_DELIVERED"}


def classify(status: str | None, status_group: str | None = None) -> str:
    """Map InPost's status (~60 values) to one of our coarse states."""
    status = (status or "").upper()
    if status in _READY or (status_group or "").upper() == "TO_PICKUP":
        return STATE_READY
    if status in _DELIVERED:
        return STATE_DELIVERED
    if status in _RETURNED:
        return STATE_RETURNED
    if status in _OUT_FOR_DELIVERY:
        return STATE_OUT_FOR_DELIVERY
    if status in _CREATED:
        return STATE_CREATED
    if status in _OTHER:
        return STATE_OTHER
    # Anything unknown is somewhere in InPost's network.
    return STATE_IN_TRANSIT


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _address(point: dict[str, Any]) -> str | None:
    details = point.get("addressDetails") or {}
    street = " ".join(
        part for part in (details.get("street"), details.get("buildingNumber")) if part
    )
    city = " ".join(part for part in (details.get("postCode"), details.get("city")) if part)
    joined = ", ".join(part for part in (street, city) if part)
    return joined or None


def parse_parcel(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise one parcel from ``/v4/parcels/tracked``."""
    point = raw.get("pickUpPoint") or {}
    location = point.get("location") or {}
    events = raw.get("events") or []
    latest = events[0] if events else {}
    status = raw.get("status")
    return {
        "shipment_number": raw.get("shipmentNumber"),
        "status": status,
        "state": classify(status, raw.get("statusGroup")),
        "status_title": latest.get("eventTitle"),
        "status_description": latest.get("eventDescription"),
        "status_date": _parse_dt(latest.get("date")),
        "sender": (raw.get("sender") or {}).get("name"),
        "shipment_type": raw.get("shipmentType"),
        "parcel_size": raw.get("parcelSize"),
        "ownership": raw.get("ownershipStatus"),
        "point_name": point.get("name"),
        "point_address": _address(point),
        "point_description": point.get("locationDescription"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "stored_date": _parse_dt(raw.get("storedDate")),
        "expiry_date": _parse_dt(raw.get("expiryDate")),
        "open_code": raw.get("openCode"),
        "qr_code": raw.get("qrCode"),
    }


def parse_parcels(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise the tracked-parcels payload, newest activity first."""
    parcels = [
        parse_parcel(item)
        for item in raw.get("parcels") or []
        if isinstance(item, dict) and item.get("shipmentNumber")
    ]
    parcels.sort(
        key=lambda p: p["status_date"].timestamp() if p["status_date"] else 0,
        reverse=True,
    )
    return parcels


def parse_notifications(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise the in-app notification list, oldest first."""
    notifications = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "content": item.get("content"),
            "date": _parse_dt(item.get("date")),
            "shipment_number": item.get("shipmentNumber"),
            "sender": item.get("sender"),
        }
        for item in raw.get("notifications") or []
        if isinstance(item, dict) and item.get("id")
    ]
    notifications.sort(key=lambda n: n["date"].timestamp() if n["date"] else 0)
    return notifications


def snapshot(parcels: list[dict[str, Any]]) -> dict[str, list[str | None]]:
    """What :func:`detect_changes` needs to remember, JSON-serialisable."""
    return {p["shipment_number"]: [p["status"], p["state"]] for p in parcels}


def detect_changes(
    parcels: list[dict[str, Any]], known: dict[str, list[str | None]]
) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(event_type, parcel)`` for every parcel that is new or moved on.

    ``known`` is a previous :func:`snapshot`. One event per parcel, the most
    specific one: arriving in a locker matters more than the fact that the
    parcel is new.
    """
    changes: list[tuple[str, dict[str, Any]]] = []
    for parcel in parcels:
        previous = known.get(parcel["shipment_number"])
        if previous is not None and previous[0] == parcel["status"]:
            continue
        previous_state = previous[1] if previous is not None else None
        state = parcel["state"]
        if state == STATE_READY and previous_state != STATE_READY:
            changes.append(("ready_to_pickup", parcel))
        elif state == STATE_DELIVERED and previous_state != STATE_DELIVERED:
            changes.append(("delivered", parcel))
        elif previous is None:
            changes.append(("new_parcel", parcel))
        else:
            changes.append(("status_changed", parcel))
    return changes

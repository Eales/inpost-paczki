"""Tests for parcel parsing and change detection (no Home Assistant needed)."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "custom_components" / "inpost_paczki" / "parcels.py"
_spec = importlib.util.spec_from_file_location("parcels", _PATH)
parcels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parcels)

# Shape of a real /v4/parcels/tracked item, with made-up personal data.
READY = {
    "shipmentNumber": "620999674032040436419350",
    "shipmentType": "parcel",
    "openCode": "123456",
    "qrCode": "P|+48600000000|123456",
    "expiryDate": "2026-09-26T07:16:24.000Z",
    "storedDate": "2026-09-24T07:16:24.000Z",
    "pickUpPoint": {
        "name": "ABC01M",
        "location": {"latitude": 50.0, "longitude": 20.0},
        "locationDescription": "Przy sklepie",
        "addressDetails": {
            "postCode": "00-001",
            "city": "Warszawa",
            "street": "Prosta",
            "buildingNumber": "1",
        },
    },
    "status": "READY_TO_PICKUP",
    "statusGroup": "TO_PICKUP",
    "ownershipStatus": "OWN",
    "parcelSize": "A",
    "sender": {"name": "Jan Kowalski"},
    "events": [
        {"date": "2026-09-24T07:16:24.023Z", "eventTitle": "Gotowa do odbioru", "eventCode": "LMD.1005"},
        {"date": "2026-09-24T04:46:48.254Z", "eventTitle": "Wydana do doręczenia", "eventCode": "LMD.1001"},
    ],
}


def _with(**changes):
    return {**READY, **changes}


def test_parse_ready_parcel():
    [parcel] = parcels.parse_parcels({"parcels": [READY], "more": False})
    assert parcel["state"] == parcels.STATE_READY
    assert parcel["sender"] == "Jan Kowalski"
    assert parcel["point_name"] == "ABC01M"
    assert parcel["point_address"] == "Prosta 1, 00-001 Warszawa"
    assert parcel["status_title"] == "Gotowa do odbioru"
    assert parcel["expiry_date"].isoformat() == "2026-09-26T07:16:24+00:00"
    assert parcel["open_code"] == "123456"


def test_parse_tolerates_missing_fields():
    [parcel] = parcels.parse_parcels({"parcels": [{"shipmentNumber": "1", "status": "CONFIRMED"}]})
    assert parcel["state"] == parcels.STATE_CREATED
    assert parcel["point_address"] is None
    assert parcel["expiry_date"] is None
    assert parcels.parse_parcels({}) == []


@pytest.mark.parametrize(
    ("status", "group", "state"),
    [
        ("CONFIRMED", None, parcels.STATE_CREATED),
        ("DISPATCHED_BY_SENDER", None, parcels.STATE_IN_TRANSIT),
        ("ADOPTED_AT_SOURCE_BRANCH", None, parcels.STATE_IN_TRANSIT),
        ("OUT_FOR_DELIVERY", None, parcels.STATE_OUT_FOR_DELIVERY),
        ("READY_TO_PICKUP", None, parcels.STATE_READY),
        ("PICKUP_REMINDER_SENT", None, parcels.STATE_READY),
        ("SOMETHING_NEW", "TO_PICKUP", parcels.STATE_READY),
        ("DELIVERED", None, parcels.STATE_DELIVERED),
        ("RETURNED_TO_SENDER", None, parcels.STATE_RETURNED),
        ("SOMETHING_NEW", None, parcels.STATE_IN_TRANSIT),
    ],
)
def test_classify(status, group, state):
    assert parcels.classify(status, group) == state


def _changes(before, after):
    known = parcels.snapshot(parcels.parse_parcels({"parcels": before}))
    return [
        (event, p["shipment_number"])
        for event, p in parcels.detect_changes(parcels.parse_parcels({"parcels": after}), known)
    ]


def test_no_change_no_event():
    assert _changes([READY], [READY]) == []


def test_new_parcel_in_transit():
    parcel = _with(status="TAKEN_BY_COURIER", statusGroup="IN_TRANSIT")
    assert _changes([], [parcel]) == [("new_parcel", READY["shipmentNumber"])]


def test_new_parcel_already_in_locker_is_ready_event():
    assert _changes([], [READY]) == [("ready_to_pickup", READY["shipmentNumber"])]


def test_arrival_in_locker():
    before = _with(status="OUT_FOR_DELIVERY", statusGroup="IN_TRANSIT")
    assert _changes([before], [READY]) == [("ready_to_pickup", READY["shipmentNumber"])]


def test_reminder_while_waiting_is_only_a_status_change():
    after = _with(status="PICKUP_REMINDER_SENT")
    assert _changes([READY], [after]) == [("status_changed", READY["shipmentNumber"])]


def test_collected():
    after = _with(status="DELIVERED", statusGroup="DELIVERED")
    assert _changes([READY], [after]) == [("delivered", READY["shipmentNumber"])]


def test_parse_notifications_oldest_first():
    raw = {
        "notifications": [
            {"id": "b", "date": "2026-09-24T07:16:24.000Z", "title": "Czeka", "content": "..."},
            {"id": "a", "date": "2026-09-23T16:48:52.000Z", "title": "W drodze", "content": "..."},
            {"title": "bez id"},
        ]
    }
    assert [n["id"] for n in parcels.parse_notifications(raw)] == ["a", "b"]

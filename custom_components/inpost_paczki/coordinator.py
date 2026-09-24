"""Data update coordinator for InPost Paczki."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InPostApi, InPostApiError, InPostAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_UID,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .parcels import (
    STATE_CREATED,
    STATE_IN_TRANSIT,
    STATE_OUT_FOR_DELIVERY,
    STATE_READY,
    detect_changes,
    parse_notifications,
    parse_parcels,
    snapshot,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# How many notification ids to remember; the API returns a handful at most.
_MAX_SEEN_NOTIFICATIONS = 200


class InPostCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches parcels and notifications for one InPost account."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=minutes),
        )
        self.entry = entry
        self.api = InPostApi(
            async_get_clientsession(hass),
            entry.data[CONF_DEVICE_UID],
            {
                "access_token": entry.data[CONF_ACCESS_TOKEN],
                "refresh_token": entry.data[CONF_REFRESH_TOKEN],
                "expires_at": entry.data.get(CONF_EXPIRES_AT, 0),
            },
            on_tokens=self._async_save_tokens,
        )
        # What was already announced survives restarts, so a restart neither
        # replays old news nor swallows what happened while HA was down.
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._known: dict[str, list[str | None]] | None = None
        self._seen_notifications: list[str] | None = None
        # Events are announced by the event entities; the first refresh runs
        # before they exist, so each one records the last refresh it announced.
        self._refresh_id = 0
        self.announced: dict[str | None, int] = {}

    async def _async_save_tokens(self, tokens: dict[str, Any]) -> None:
        """Persist a rotated token set; the previous refresh token is now dead."""
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_ACCESS_TOKEN: tokens["access_token"],
                CONF_REFRESH_TOKEN: tokens["refresh_token"],
                CONF_EXPIRES_AT: tokens["expires_at"],
            },
        )

    async def _async_update_data(self) -> dict[str, Any]:
        if self._known is None:
            stored = await self._store.async_load() or {}
            self._known = stored.get("parcels")
            self._seen_notifications = stored.get("notifications")

        try:
            parcels = parse_parcels(await self.api.async_get_tracked())
            notifications = parse_notifications(await self.api.async_get_notifications())
        except InPostAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except InPostApiError as err:
            raise UpdateFailed(str(err)) from err

        # Very first run of a new entry: take the current state as the baseline
        # instead of announcing every parcel that is already in the account.
        first_run = self._known is None
        changes = [] if first_run else detect_changes(parcels, self._known or {})

        seen = set(self._seen_notifications or [])
        new_notifications = (
            [] if self._seen_notifications is None
            else [n for n in notifications if n["id"] not in seen]
        )

        # Parcels that drop off the list are forgotten, so the snapshot does not grow.
        self._known = snapshot(parcels)
        ids = [n for n in (self._seen_notifications or []) if n] + [
            n["id"] for n in notifications if n["id"] not in seen
        ]
        self._seen_notifications = ids[-_MAX_SEEN_NOTIFICATIONS:]
        await self._store.async_save(
            {"parcels": self._known, "notifications": self._seen_notifications}
        )

        ready = [p for p in parcels if p["state"] == STATE_READY]
        ready.sort(key=lambda p: p["expiry_date"].timestamp() if p["expiry_date"] else float("inf"))
        on_the_way = [
            p for p in parcels
            if p["state"] in (STATE_CREATED, STATE_IN_TRANSIT, STATE_OUT_FOR_DELIVERY)
        ]
        self._refresh_id += 1
        return {
            "refresh_id": self._refresh_id,
            "parcels": parcels,
            "ready": ready,
            "on_the_way": on_the_way,
            "changes": changes,
            "notifications": notifications,
            "new_notifications": new_notifications,
        }

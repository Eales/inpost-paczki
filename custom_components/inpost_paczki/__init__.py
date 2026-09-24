"""The InPost Paczki integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_SCAN_INTERVAL, CONF_SHOW_CODES, DOMAIN
from .coordinator import STORAGE_VERSION, InPostCoordinator

PLATFORMS = ["binary_sensor", "calendar", "event", "sensor"]

type InPostConfigEntry = ConfigEntry[InPostCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: InPostConfigEntry) -> bool:
    """Set up InPost Paczki from a config entry."""
    coordinator = InPostCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    options = {key: entry.options.get(key) for key in (CONF_SCAN_INTERVAL, CONF_SHOW_CODES)}

    async def _async_entry_updated(hass: HomeAssistant, entry: InPostConfigEntry) -> None:
        # Rotated tokens are written to entry.data on every refresh; only a real
        # change of options is worth a reload.
        current = {key: entry.options.get(key) for key in options}
        if current != options:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InPostConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: InPostConfigEntry) -> None:
    """Drop the remembered parcel states together with the entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()

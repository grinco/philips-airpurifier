"""The Philips AirPurifier integration (encrypted HTTP protocol devices)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import PhilipsAirClient, PhilipsError
from .coordinator import PhilipsConfigEntry, PhilipsCoordinator

PLATFORMS: list[Platform] = [Platform.FAN]


async def async_setup_entry(hass: HomeAssistant, entry: PhilipsConfigEntry) -> bool:
    """Set up a purifier from a config entry."""
    client = PhilipsAirClient(entry.data[CONF_HOST])
    try:
        firmware = await client.get_firmware()
        wifi = await client.get_wifi()
    except PhilipsError as err:
        await client.close()
        raise ConfigEntryNotReady(
            f"Cannot connect to {entry.data[CONF_HOST]}: {err}"
        ) from err

    coordinator = PhilipsCoordinator(hass, entry, client, firmware, wifi)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: PhilipsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PhilipsConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded

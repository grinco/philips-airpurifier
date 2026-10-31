"""Polling coordinator with automatic recovery for Philips air purifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import PhilipsAirClient, PhilipsError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, FAILURES_BEFORE_RELOAD

_LOGGER = logging.getLogger(__name__)


@dataclass
class PhilipsData:
    """Latest values read from the device."""

    status: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)


type PhilipsConfigEntry = ConfigEntry[PhilipsCoordinator]


class PhilipsCoordinator(DataUpdateCoordinator[PhilipsData]):
    """Polls the purifier and recovers from a hung connection.

    Every failed poll drops the session key and HTTP session, so the next
    poll starts with a fresh key exchange. If the device still does not
    answer after FAILURES_BEFORE_RELOAD polls in a row, the whole config
    entry is reloaded. While the device stays offline, Home Assistant then
    keeps retrying the setup with a growing back-off.
    """

    config_entry: PhilipsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PhilipsConfigEntry,
        client: PhilipsAirClient,
        firmware: dict[str, Any],
        wifi: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.firmware = firmware
        self.wifi = wifi
        self._failures = 0
        self._reload_scheduled = False

    async def _async_update_data(self) -> PhilipsData:
        try:
            status = await self.client.get_status()
            filters = await self.client.get_filters()
        except PhilipsError as err:
            self._failures += 1
            await self.client.reset()
            self._maybe_reload()
            raise UpdateFailed(
                f"Error talking to {self.client.host} "
                f"({self._failures} failure(s) in a row): {err}"
            ) from err

        if self._failures:
            _LOGGER.info(
                "%s is responding again after %d failed poll(s)",
                self.client.host,
                self._failures,
            )
        self._failures = 0
        return PhilipsData(status=status, filters=filters)

    def _maybe_reload(self) -> None:
        if (
            self._failures < FAILURES_BEFORE_RELOAD
            or self._reload_scheduled
            or self.config_entry.state is not ConfigEntryState.LOADED
        ):
            return
        self._reload_scheduled = True
        _LOGGER.warning(
            "%s did not respond to %d polls in a row, reloading the integration",
            self.client.host,
            self._failures,
        )
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    async def async_set_values(self, values: dict[str, Any]) -> None:
        """Send values to the device and publish the state it reports back."""
        try:
            status = await self.client.set_values(values)
        except PhilipsError as err:
            await self.client.reset()
            self.hass.async_create_task(self.async_request_refresh())
            raise HomeAssistantError(
                f"Could not send {values} to {self.client.host}: {err}"
            ) from err
        data = self.data or PhilipsData()
        self.async_set_updated_data(
            PhilipsData(status={**data.status, **status}, filters=data.filters)
        )

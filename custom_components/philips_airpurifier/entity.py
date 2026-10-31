"""Base entity for Philips air purifiers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, PHILIPS_MAC_ADDRESS, PHILIPS_MODEL_NAME
from .coordinator import PhilipsCoordinator


class PhilipsEntity(CoordinatorEntity[PhilipsCoordinator]):
    """Common device info for all entities of one purifier."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PhilipsCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._mac: str = coordinator.wifi.get(PHILIPS_MAC_ADDRESS) or entry.unique_id
        self._model: str | None = (
            str(coordinator.firmware.get(PHILIPS_MODEL_NAME, "")).replace("_", "/") or None
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or self._mac)},
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            manufacturer=MANUFACTURER,
            model=self._model,
            name=entry.title,
            sw_version=coordinator.firmware.get("version"),
            configuration_url=f"http://{coordinator.client.host}",
        )

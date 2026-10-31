"""Fan entity for Philips air purifiers and humidifiers."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.fan import (
    PLATFORM_SCHEMA as FAN_PLATFORM_SCHEMA,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import *  # noqa: F403  pylint: disable=wildcard-import,unused-wildcard-import
from .coordinator import PhilipsConfigEntry, PhilipsCoordinator
from .entity import PhilipsEntity

_LOGGER = logging.getLogger(__name__)

# Legacy YAML config, only used to import into a config entry.
PLATFORM_SCHEMA = FAN_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

ENTITY_SERVICES: dict[str, tuple[dict, str]] = {
    SERVICE_SET_FUNCTION: (
        {vol.Required(SERVICE_ATTR_FUNCTION): vol.In(list(FUNCTION_MAP.values()))},
        "async_set_function",
    ),
    SERVICE_SET_TARGET_HUMIDITY: (
        {
            vol.Required(SERVICE_ATTR_HUMIDITY): vol.All(
                vol.Coerce(int), vol.In(TARGET_HUMIDITY_LIST)
            )
        },
        "async_set_target_humidity",
    ),
    SERVICE_SET_LIGHT_BRIGHTNESS: (
        {
            vol.Required(SERVICE_ATTR_BRIGHTNESS_LEVEL): vol.All(
                vol.Coerce(int), vol.In(LIGHT_BRIGHTNESS_LIST)
            )
        },
        "async_set_light_brightness",
    ),
    SERVICE_SET_CHILD_LOCK: (
        {vol.Required(SERVICE_ATTR_CHILD_LOCK): cv.boolean},
        "async_set_child_lock",
    ),
    SERVICE_SET_TIMER: (
        {
            vol.Required(SERVICE_ATTR_TIMER_HOURS): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=12)
            )
        },
        "async_set_timer",
    ),
    SERVICE_SET_DISPLAY_LIGHT: (
        {vol.Required(SERVICE_ATTR_DISPLAY_LIGHT): cv.boolean},
        "async_set_display_light",
    ),
}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import a YAML configured device into a config entry."""
    host = config[CONF_HOST]
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: host, CONF_NAME: config[CONF_NAME]},
    )
    if (
        result["type"] is FlowResultType.ABORT
        and result.get("reason") != "already_configured"
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_failed_{host}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml_import_failed",
            translation_placeholders={"host": host},
        )
        return

    ir.async_delete_issue(hass, DOMAIN, f"deprecated_yaml_import_failed_{host}")
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"deprecated_yaml_{host}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={"host": host},
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhilipsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan entity from a config entry."""
    async_add_entities([PhilipsAirPurifierFan(entry.runtime_data)])

    platform = entity_platform.async_get_current_platform()
    for name, (schema, method) in ENTITY_SERVICES.items():
        platform.async_register_entity_service(name, schema, method)


def _find_key(value_map: dict, search_value: Any) -> Any:
    for key, value in value_map.items():
        if value == search_value:
            return key
    return None


class PhilipsAirPurifierFan(PhilipsEntity, FanEntity):
    """Philips air purifier fan entity."""

    _attr_name = None
    _attr_icon = DEFAULT_ICON
    _attr_preset_modes = SUPPORTED_PRESET_LIST
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: PhilipsCoordinator) -> None:
        super().__init__(coordinator)
        # Same unique_id as the old YAML platform, so existing entities are reused.
        self._attr_unique_id = self._mac

        self._fan_speed: str | None = None
        self._preset_mode: str | None = None
        self._is_on: bool | None = None
        self._values: dict[str, Any] = {}
        self._parse()

    # ---- state ----

    @callback
    def _handle_coordinator_update(self) -> None:
        self._parse()
        super()._handle_coordinator_update()

    def _parse(self) -> None:
        data = self.coordinator.data
        if data is None:
            return
        status = data.status
        filters = data.filters

        if PHILIPS_POWER in status:
            self._is_on = status[PHILIPS_POWER] == "1"

        if PHILIPS_MODE in status:
            mode = status[PHILIPS_MODE]
            self._preset_mode = MODE_MAP.get(mode, mode)
            if mode == PHILIPS_MODE_MANUAL and PHILIPS_SPEED in status:
                speed = status[PHILIPS_SPEED]
                if speed != PHILIPS_SPEED_OFF:
                    self._fan_speed = SPEED_MAP.get(speed, speed)
                self._preset_mode = self._fan_speed

        v: dict[str, Any] = {}
        if self._model:
            v[ATTR_MODEL] = self._model
        if PHILIPS_FUNCTION in status:
            v[ATTR_FUNCTION] = FUNCTION_MAP.get(status[PHILIPS_FUNCTION], status[PHILIPS_FUNCTION])
        if PHILIPS_USED_INDEX in status:
            v[ATTR_USED_INDEX] = USED_INDEX_MAP.get(status[PHILIPS_USED_INDEX], status[PHILIPS_USED_INDEX])
        for attr, key in (
            (ATTR_PM25, PHILIPS_PM25),
            (ATTR_ALLERGEN_INDEX, PHILIPS_ALLERGEN_INDEX),
            (ATTR_TEMPERATURE, PHILIPS_TEMPERATURE),
            (ATTR_HUMIDITY, PHILIPS_HUMIDITY),
            (ATTR_TARGET_HUMIDITY, PHILIPS_TARGET_HUMIDITY),
            (ATTR_WATER_LEVEL, PHILIPS_WATER_LEVEL),
            (ATTR_LIGHT_BRIGHTNESS, PHILIPS_LIGHT_BRIGHTNESS),
            (ATTR_CHILD_LOCK, PHILIPS_CHILD_LOCK),
            (ATTR_TIMER, PHILIPS_TIMER),
            (ATTR_TIMER_REMAINGING_MINUTES, PHILIPS_TIMER_REMAINING),
        ):
            if key in status:
                v[attr] = status[key]
        if PHILIPS_DISPLAY_LIGHT in status:
            v[ATTR_DISPLAY_LIGHT] = DISPLAY_LIGHT_MAP.get(
                status[PHILIPS_DISPLAY_LIGHT], status[PHILIPS_DISPLAY_LIGHT]
            )
        for attr, key in (
            (ATTR_PRE_FILTER, "fltsts0"),
            (ATTR_HEPA_FILTER, "fltsts1"),
            (ATTR_CARBON_FILTER, "fltsts2"),
            (ATTR_WICK_FILTER, "wicksts"),
        ):
            if key in filters:
                v[attr] = filters[key]
        self._values = v

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._values

    # ---- commands ----

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan, optionally with a preset."""
        if preset_mode is not None:
            await self._async_set_preset(preset_mode, turn_on=True)
        else:
            await self.coordinator.async_set_values({PHILIPS_POWER: "1"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self.coordinator.async_set_values({PHILIPS_POWER: "0"})

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        await self._async_set_preset(preset_mode)

    async def _async_set_preset(self, preset_mode: str, turn_on: bool = False) -> None:
        values: dict[str, Any] = {}
        if turn_on:
            values[PHILIPS_POWER] = "1"
        if preset_mode == self._preset_mode:
            pass
        elif preset_mode in SPEED_MAP.values():
            self._fan_speed = preset_mode
            values[PHILIPS_MODE] = PHILIPS_MODE_MANUAL
            values[PHILIPS_SPEED] = _find_key(SPEED_MAP, preset_mode)
        elif preset_mode in MODE_MAP.values():
            values[PHILIPS_MODE] = _find_key(MODE_MAP, preset_mode)
        else:
            _LOGGER.warning("Unsupported preset %s", preset_mode)
        if values:
            await self.coordinator.async_set_values(values)

    async def async_set_function(self, function: str) -> None:
        """Set the device function."""
        if function != self._values.get(ATTR_FUNCTION):
            await self.coordinator.async_set_values(
                {PHILIPS_FUNCTION: _find_key(FUNCTION_MAP, function)}
            )

    async def async_set_target_humidity(self, humidity: int) -> None:
        """Set the target humidity."""
        if humidity != self._values.get(ATTR_TARGET_HUMIDITY):
            await self.coordinator.async_set_values({PHILIPS_TARGET_HUMIDITY: humidity})

    async def async_set_light_brightness(self, level: int) -> None:
        """Set the light brightness; 0 also turns the display light off."""
        if level != self._values.get(ATTR_LIGHT_BRIGHTNESS):
            await self.coordinator.async_set_values(
                {
                    PHILIPS_LIGHT_BRIGHTNESS: level,
                    PHILIPS_DISPLAY_LIGHT: _find_key(DISPLAY_LIGHT_MAP, level != 0),
                }
            )

    async def async_set_child_lock(self, lock: bool) -> None:
        """Set the child lock."""
        if lock != self._values.get(ATTR_CHILD_LOCK):
            await self.coordinator.async_set_values({PHILIPS_CHILD_LOCK: lock})

    async def async_set_timer(self, hours: int) -> None:
        """Set the off timer."""
        await self.coordinator.async_set_values({PHILIPS_TIMER: hours})

    async def async_set_display_light(self, light: bool) -> None:
        """Set the display light."""
        if light != self._values.get(ATTR_DISPLAY_LIGHT):
            await self.coordinator.async_set_values(
                {PHILIPS_DISPLAY_LIGHT: _find_key(DISPLAY_LIGHT_MAP, light)}
            )

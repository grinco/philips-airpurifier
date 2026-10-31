"""Fan and sensor entities, commands and services."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.philips_airpurifier.const import DOMAIN

from .conftest import add_entry

FAN = "fan.ac2889_10"


async def test_fan_state(hass: HomeAssistant, device) -> None:
    await add_entry(hass, device.host)
    state = hass.states.get(FAN)
    assert state.state == "on"
    assert state.attributes["preset_mode"] == "Speed 2"
    assert state.attributes["pm25"] == 3
    assert state.attributes["hepa_filter"] == 7111
    assert er.async_get(hass).async_get(FAN).unique_id == device.mac


async def test_sensors_ac2889(hass: HomeAssistant, device) -> None:
    entry = await add_entry(hass, device.host)
    entities = {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "sensor"
    }
    assert entities == {
        "sensor.ac2889_10_pm2_5",
        "sensor.ac2889_10_allergen_index",
        "sensor.ac2889_10_pre_filter_cleaning",
        "sensor.ac2889_10_hepa_filter",
        "sensor.ac2889_10_active_carbon_filter",
    }
    pm = hass.states.get("sensor.ac2889_10_pm2_5")
    assert pm.state == "3"
    assert pm.attributes["unit_of_measurement"] == "µg/m³"
    assert pm.attributes["device_class"] == "pm25"


async def test_sensors_humidifier(hass: HomeAssistant, humidifier) -> None:
    await add_entry(hass, humidifier.host)
    assert hass.states.get("sensor.ac3829_10_temperature").state == "22"
    assert hass.states.get("sensor.ac3829_10_humidity").state == "45"
    assert hass.states.get("sensor.ac3829_10_water_level").state == "100"
    assert hass.states.get("sensor.ac3829_10_wick_filter").state == "4800"
    assert hass.states.get("fan.ac3829_10").attributes["function"] == (
        "Purification & Humidification"
    )


async def test_turn_off_on(hass: HomeAssistant, device) -> None:
    await add_entry(hass, device.host)
    await hass.services.async_call("fan", "turn_off", {"entity_id": FAN}, blocking=True)
    assert device.status["pwr"] == "0"
    assert hass.states.get(FAN).state == "off"

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": FAN, "preset_mode": "Auto"}, blocking=True
    )
    assert device.puts[-1] == {"pwr": "1", "mode": "P"}
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(FAN).attributes["preset_mode"] == "Auto"


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("Turbo", {"mode": "M", "om": "t"}),
        ("Speed 1", {"mode": "M", "om": "1"}),
        ("Allergen", {"mode": "A"}),
        ("Bacteria", {"mode": "B"}),
        ("Sleep", {"mode": "S"}),
    ],
)
async def test_preset_modes(hass: HomeAssistant, device, preset, expected) -> None:
    await add_entry(hass, device.host)
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": FAN, "preset_mode": preset}, blocking=True
    )
    assert device.puts[-1] == expected
    assert hass.states.get(FAN).attributes["preset_mode"] == preset


async def test_unchanged_preset_sends_nothing(hass: HomeAssistant, device) -> None:
    await add_entry(hass, device.host)
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": FAN, "preset_mode": "Speed 2"}, blocking=True
    )
    assert device.puts == []


@pytest.mark.parametrize(
    ("service", "data", "expected"),
    [
        ("set_child_lock", {"lock": True}, {"cl": True}),
        ("set_light_brightness", {"level": 0}, {"aqil": 0, "uil": "0"}),
        ("set_light_brightness", {"level": "50"}, {"aqil": 50, "uil": "1"}),
        ("set_display_light", {"light": False}, {"uil": "0"}),
        ("set_timer", {"hours": 3}, {"dt": 3}),
    ],
)
async def test_services(hass: HomeAssistant, device, service, data, expected) -> None:
    await add_entry(hass, device.host)
    await hass.services.async_call(
        DOMAIN, service, {"entity_id": FAN, **data}, blocking=True
    )
    assert device.puts[-1] == expected


async def test_humidifier_services(hass: HomeAssistant, humidifier) -> None:
    await add_entry(hass, humidifier.host)
    fan = "fan.ac3829_10"
    await hass.services.async_call(
        DOMAIN, "set_function", {"entity_id": fan, "function": "Purification"}, blocking=True
    )
    assert humidifier.puts[-1] == {"func": "P"}
    await hass.services.async_call(
        DOMAIN, "set_target_humidity", {"entity_id": fan, "humidity": 60}, blocking=True
    )
    assert humidifier.puts[-1] == {"rhset": 60}


async def test_command_failure_raises(hass: HomeAssistant, device) -> None:
    await add_entry(hass, device.host)
    device.failing = True
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "fan", "turn_off", {"entity_id": FAN}, blocking=True
        )
    device.failing = False
    await hass.async_block_till_done()

"""Config, options, reconfigure and YAML import flows."""

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.philips_airpurifier.const import DOMAIN

from .conftest import add_entry
from .fake_device import FakePurifier

UNREACHABLE = "127.0.0.1:1"


async def _start_reconfigure(hass: HomeAssistant, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )


async def test_user_flow(hass: HomeAssistant, device) -> None:
    entry = await add_entry(hass, device.host)
    assert entry.title == "AC2889/10"
    assert entry.unique_id == "e8:c1:d7:00:73:b8"
    assert entry.data == {"host": device.host}

    # Adding the same device again is rejected.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": device.host}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_user_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": UNREACHABLE}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure(hass: HomeAssistant, device, humidifier) -> None:
    entry = await add_entry(hass, device.host)

    # A different purifier at the new address is refused.
    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": humidifier.host}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "wrong_device"

    # Same purifier at a new address is accepted.
    moved = FakePurifier(mac=device.mac)
    await moved.start()
    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": moved.host}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == moved.host
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await moved.stop()


async def test_options_flow(hass: HomeAssistant, device) -> None:
    entry = await add_entry(hass, device.host)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options[CONF_SCAN_INTERVAL] == 60
    assert entry.runtime_data.update_interval.total_seconds() == 60


async def test_yaml_import(hass: HomeAssistant, device) -> None:
    assert await async_setup_component(
        hass,
        "fan",
        {"fan": {"platform": DOMAIN, "host": device.host, "name": "Living room"}},
    )
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].title == "Living room"
    assert hass.states.get("fan.living_room") is not None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"deprecated_yaml_{device.host}")


async def test_yaml_import_unreachable(hass: HomeAssistant, socket_enabled) -> None:
    assert await async_setup_component(
        hass, "fan", {"fan": {"platform": DOMAIN, "host": UNREACHABLE}}
    )
    await hass.async_block_till_done()

    assert not hass.config_entries.async_entries(DOMAIN)
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"deprecated_yaml_import_failed_{UNREACHABLE}"
    )

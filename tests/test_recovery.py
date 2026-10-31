"""Reconnecting, re-keying and reloading when the device misbehaves."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.philips_airpurifier.const import FAILURES_BEFORE_RELOAD

from .conftest import add_entry

FAN = "fan.ac2889_10"


async def test_rekey_after_device_reboot(hass: HomeAssistant, device) -> None:
    """A rebooted device forgets the key; the next poll re-keys transparently."""
    entry = await add_entry(hass, device.host)
    handshakes = device.handshakes
    device.reboot()
    device.status["pm25"] = 42
    await entry.runtime_data.async_refresh()
    assert device.handshakes == handshakes + 1
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get("sensor.ac2889_10_pm2_5").state == "42"


async def test_reload_after_consecutive_failures(hass: HomeAssistant, device) -> None:
    entry = await add_entry(hass, device.host)
    coordinator = entry.runtime_data
    device.failing = True
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        for attempt in range(1, FAILURES_BEFORE_RELOAD + 2):
            await coordinator.async_refresh()
            assert hass.states.get(FAN).state == "unavailable"
            assert reload.call_count == (1 if attempt >= FAILURES_BEFORE_RELOAD else 0)
        reload.assert_called_once_with(entry.entry_id)

    device.failing = False
    await coordinator.async_refresh()
    assert hass.states.get(FAN).state == "on"


async def test_real_reload_cycle(hass: HomeAssistant, device) -> None:
    """Unpatched: the entry reloads itself and comes back once the device answers."""
    entry = await add_entry(hass, device.host)
    coordinator = entry.runtime_data
    device.failing = True
    for _ in range(FAILURES_BEFORE_RELOAD):
        await coordinator.async_refresh()
    device.failing = False  # device is back by the time the reload runs
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not coordinator
    assert hass.states.get(FAN).state == "on"


async def test_reload_while_offline_retries(hass: HomeAssistant, device) -> None:
    """If the device stays down, the reload ends in setup retry."""
    entry = await add_entry(hass, device.host)
    device.failing = True
    for _ in range(FAILURES_BEFORE_RELOAD):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get(FAN).state == "unavailable"


async def test_offline_at_startup(hass: HomeAssistant, device) -> None:
    entry = await add_entry(hass, device.host)
    await hass.config_entries.async_unload(entry.entry_id)
    device.failing = True
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY

    device.failing = False
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

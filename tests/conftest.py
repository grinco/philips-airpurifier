"""Fixtures for the Philips AirPurifier tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.philips_airpurifier.const import DOMAIN

from .fake_device import AC3829_FILTERS, AC3829_STATUS, FakePurifier

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in every test."""
    yield


@pytest.fixture
async def device(socket_enabled) -> AsyncGenerator[FakePurifier]:
    """An AC2889-like purifier (no humidifier)."""
    dev = FakePurifier()
    await dev.start()
    yield dev
    await dev.stop()


@pytest.fixture
async def humidifier(socket_enabled) -> AsyncGenerator[FakePurifier]:
    """An AC3829-like purifier with humidifier."""
    dev = FakePurifier(
        model="AC3829_10",
        mac="aa:bb:cc:dd:ee:ff",
        status=AC3829_STATUS,
        filters=AC3829_FILTERS,
    )
    await dev.start()
    yield dev
    await dev.stop()


async def add_entry(hass: HomeAssistant, host: str) -> ConfigEntry:
    """Run the user config flow and return the created, loaded entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": host}
    )
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return result["result"]

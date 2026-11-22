"""Integration tests for GetBrowserCommand."""

import pytest
from browserpool.service import (
    BrowserNotFound,
    GetBrowserCommand,
    GetBrowserParameters,
)
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import seed_browser


@pytest.mark.asyncio
async def test_get_browser_returns_active_browser(
    service_app_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    async with service_app_container() as setup:
        await seed_browser(setup, service_settings, container_id="get-1")

    async with service_app_container() as scope:
        command = await scope.get(GetBrowserCommand)
        browser = await command(GetBrowserParameters(container_id="get-1"))

    assert browser.container_id == "get-1"
    assert browser.variant == "camoufox"
    assert browser.active is True
    assert browser.sandbox.network_id != ""


@pytest.mark.asyncio
async def test_get_browser_missing_raises(
    service_app_container: AsyncContainer,
) -> None:
    async with service_app_container() as scope:
        command = await scope.get(GetBrowserCommand)
        with pytest.raises(BrowserNotFound):
            await command(GetBrowserParameters(container_id="missing"))


@pytest.mark.asyncio
async def test_get_browser_inactive_raises(
    service_app_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    async with service_app_container() as setup:
        await seed_browser(
            setup, service_settings, container_id="get-inactive", active=False
        )

    async with service_app_container() as scope:
        command = await scope.get(GetBrowserCommand)
        with pytest.raises(BrowserNotFound):
            await command(GetBrowserParameters(container_id="get-inactive"))

"""Integration tests for ListBrowsersCommand."""

import pytest
from browserpool.service import ListBrowsersCommand
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import seed_browser


@pytest.mark.asyncio
async def test_list_browsers_returns_only_active(
    service_app_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    async with service_app_container() as setup:
        first_network = await seed_browser(
            setup, service_settings, container_id="list-1"
        )
        await seed_browser(setup, service_settings, container_id="list-2")
        await seed_browser(
            setup,
            service_settings,
            container_id="list-inactive",
            active=False,
            network_id=first_network,
        )

    async with service_app_container() as scope:
        command = await scope.get(ListBrowsersCommand)
        browsers = await command()

    assert {browser.container_id for browser in browsers} == {"list-1", "list-2"}


@pytest.mark.asyncio
async def test_list_browsers_empty(service_app_container: AsyncContainer) -> None:
    async with service_app_container() as scope:
        command = await scope.get(ListBrowsersCommand)
        assert await command() == []

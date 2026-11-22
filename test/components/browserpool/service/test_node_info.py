"""Integration tests for NodeInfoCommand."""

import pytest
from browserpool.service import NodeInfoCommand
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import seed_browser


@pytest.mark.asyncio
async def test_node_info_reports_capacity(
    service_app_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    async with service_app_container() as setup:
        await seed_browser(setup, service_settings, container_id="info-1")

    async with service_app_container() as scope:
        command = await scope.get(NodeInfoCommand)
        info = await command()

    assert info.version == "0.1.0"
    assert info.browser_limit == service_settings.browser_limit
    assert info.sandboxes_active == service_settings.browser_limit
    assert info.browsers_active == 1
    assert info.sandboxes_free == service_settings.browser_limit - 1
    assert {variant["name"] for variant in info.variants} == {
        "camoufox",
        "chromium",
    }


@pytest.mark.asyncio
async def test_node_info_empty(
    service_app_container: AsyncContainer,
) -> None:
    async with service_app_container() as scope:
        command = await scope.get(NodeInfoCommand)
        info = await command()

    assert info.sandboxes_active == 0
    assert info.sandboxes_free == 0
    assert info.browsers_active == 0

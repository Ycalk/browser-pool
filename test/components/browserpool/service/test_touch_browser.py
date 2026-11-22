"""Integration tests for TouchBrowserCommand."""

from datetime import UTC, datetime, timedelta

import pytest
from browserpool.service import (
    BrowserNotFound,
    TouchBrowserCommand,
    TouchBrowserParameters,
)
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import seed_browser


@pytest.mark.asyncio
async def test_touch_browser_updates_last_touched_at(
    service_request_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    old = datetime.now(UTC) - timedelta(hours=1)
    await seed_browser(
        service_request_container,
        service_settings,
        container_id="touch-1",
        last_touched_at=old,
    )
    command = await service_request_container.get(TouchBrowserCommand)
    browser = await command(TouchBrowserParameters(container_id="touch-1"))

    assert browser.last_touched_at > int(old.timestamp())


@pytest.mark.asyncio
async def test_touch_browser_missing_raises(
    service_request_container: AsyncContainer,
) -> None:
    command = await service_request_container.get(TouchBrowserCommand)
    with pytest.raises(BrowserNotFound):
        await command(TouchBrowserParameters(container_id="missing"))

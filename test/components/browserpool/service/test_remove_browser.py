"""Integration tests for RemoveBrowserCommand."""

import pytest
from browserpool.container_driver import (
    LabelFilters,
    ListContainersCommand,
    ListContainersParameters,
)
from browserpool.database import BrowserDAO, SandboxDAO, WriteSession
from browserpool.service import (
    BrowserNotFound,
    RemoveBrowserCommand,
    RemoveBrowserParameters,
)
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import (
    create_browser,
    patch_camoufox_to_alpine_listener,
    provision_sandboxes,
    seed_browser,
)


@pytest.mark.asyncio
async def test_remove_browser_removes_container_and_deactivates_row(
    monkeypatch: pytest.MonkeyPatch,
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    patch_camoufox_to_alpine_listener(monkeypatch)
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    browser = await create_browser(
        service_request_container,
        service_settings,
        sandbox_write_dao,
        browser_write_dao,
    )
    command = await service_request_container.get(RemoveBrowserCommand)
    removed = await command(RemoveBrowserParameters(container_id=browser.container_id))

    assert removed.active is False
    found = await browser_write_dao.find_by_id(browser.container_id)
    assert found is not None and found.active is False

    list_containers = await service_request_container.get(ListContainersCommand)
    containers = await list_containers(
        ListContainersParameters(
            all=True,
            filters=LabelFilters(labels={service_settings.managed_label: "true"}),
        )
    )
    assert all(container.id != browser.container_id for container in containers)


@pytest.mark.asyncio
async def test_remove_browser_missing_raises(
    service_request_container: AsyncContainer,
) -> None:
    command = await service_request_container.get(RemoveBrowserCommand)
    with pytest.raises(BrowserNotFound):
        await command(RemoveBrowserParameters(container_id="missing"))


@pytest.mark.asyncio
async def test_remove_browser_inactive_is_idempotent(
    service_request_container: AsyncContainer,
    service_settings: ServiceSettings,
) -> None:
    await seed_browser(
        service_request_container,
        service_settings,
        container_id="remove-inactive",
        active=False,
    )
    command = await service_request_container.get(RemoveBrowserCommand)
    removed = await command(RemoveBrowserParameters(container_id="remove-inactive"))

    assert removed.active is False

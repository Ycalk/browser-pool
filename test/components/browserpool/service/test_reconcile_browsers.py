"""Integration tests for ReconcileBrowsersCommand against a real Docker daemon.

ReconcileBrowsers reconciles managed browser containers with the database: a
browser row whose container vanished is deactivated, and a managed container
with no readable adoption labels is removed as an orphan.
"""

import pytest
from browserpool.container_driver import (
    InspectContainerCommand,
    ListContainersCommand,
    RemoveContainerCommand,
    RemoveContainerParameters,
)
from browserpool.database import (
    BrowserDAO,
    ReadSession,
    SandboxDAO,
    WriteSession,
)
from browserpool.service.commands.reconcile_browsers import (
    ReconcileBrowsersCommand,
)
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import (
    create_browser,
    make_alpine_container,
    patch_camoufox_to_alpine_listener,
    provision_sandboxes,
)


@pytest.mark.asyncio
async def test_reconcile_browsers_deactivates_row_when_container_gone(
    monkeypatch: pytest.MonkeyPatch,
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    sandbox_read_dao: SandboxDAO[ReadSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """A browser row whose container vanished is marked inactive."""
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
    remove_container = await service_request_container.get(RemoveContainerCommand)
    await remove_container(
        RemoveContainerParameters(id=browser.container_id, force=True)
    )
    cmd = ReconcileBrowsersCommand(
        settings=service_settings,
        browser_dao=browser_write_dao,
        sandbox_dao=sandbox_read_dao,
        list_containers=await service_request_container.get(ListContainersCommand),
        inspect_container=await service_request_container.get(InspectContainerCommand),
        remove_container=remove_container,
    )
    result = await cmd()
    assert any(b.container_id == browser.container_id for b in result.deactivated)
    found = await browser_write_dao.find_by_id(browser.container_id)
    assert found is not None and found.active is False


@pytest.mark.asyncio
async def test_reconcile_browsers_removes_orphan_container_without_row(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    sandbox_read_dao: SandboxDAO[ReadSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """A managed container with no DB row and unreadable labels is removed."""
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    sandbox = (await sandbox_write_dao.find_active_without_browsers())[0]
    container_id = await make_alpine_container(
        service_request_container,
        service_settings,
        sandbox,
        f"orphan-{sandbox.index}",
    )
    remove_container = await service_request_container.get(RemoveContainerCommand)
    cmd = ReconcileBrowsersCommand(
        settings=service_settings,
        browser_dao=browser_write_dao,
        sandbox_dao=sandbox_read_dao,
        list_containers=await service_request_container.get(ListContainersCommand),
        inspect_container=await service_request_container.get(InspectContainerCommand),
        remove_container=remove_container,
    )
    result = await cmd()
    assert container_id in result.removed

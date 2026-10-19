"""Integration tests for CreateBrowserCommand against a real Docker daemon.

CreateBrowser provisions a container in an empty sandbox slot and records a
browser row. The camoufox variant is patched to run `alpine:3.20` with a busybox
`nc` loop so the TCP readiness probe succeeds without the real browser image.
"""

from datetime import UTC, datetime

import pytest
from browserpool.container_driver import (
    CreateContainerCommand,
    InspectContainerCommand,
    LabelFilters,
    ListContainersCommand,
    ListContainersParameters,
    RemoveContainerCommand,
    StartContainerCommand,
)
from browserpool.database import (
    BrowserCreateParameters,
    BrowserDAO,
    SandboxDAO,
    WriteSession,
)
from browserpool.service.commands.create_browser import (
    CreateBrowserCommand,
    CreateBrowserParameters,
)
from browserpool.service.exceptions import BrowserLimitExceeded, InvalidIdleTTL
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import (
    create_browser,
    patch_camoufox_to_alpine_listener,
    provision_sandboxes,
)


@pytest.mark.asyncio
async def test_create_browser_creates_container_and_row(
    monkeypatch: pytest.MonkeyPatch,
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """create_browser provisions a container and a browser row in an empty slot."""
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
    assert browser.active is True
    assert browser.variant == "camoufox"
    assert browser.host != ""
    assert browser.port == 9222
    list_containers = await service_request_container.get(ListContainersCommand)
    containers = await list_containers(
        ListContainersParameters(
            all=True,
            filters=LabelFilters(labels={service_settings.managed_label: "true"}),
        )
    )
    assert any(c.id == browser.container_id for c in containers)
    found = await browser_write_dao.find_by_id(browser.container_id)
    assert found is not None and found.active is True


@pytest.mark.asyncio
async def test_create_browser_rejects_ttl_below_minimum(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """idle_ttl_seconds below the configured minimum raises InvalidIdleTTL."""
    too_low = service_settings.browser_min_idle_ttl_seconds - 1
    cmd = CreateBrowserCommand(
        settings=service_settings,
        create_container=await service_request_container.get(CreateContainerCommand),
        start_container=await service_request_container.get(StartContainerCommand),
        inspect_container=await service_request_container.get(InspectContainerCommand),
        remove_container=await service_request_container.get(RemoveContainerCommand),
        sandbox_dao=sandbox_write_dao,
        browser_dao=browser_write_dao,
    )
    with pytest.raises(InvalidIdleTTL):
        await cmd(CreateBrowserParameters(variant="camoufox", idle_ttl_seconds=too_low))


@pytest.mark.asyncio
async def test_create_browser_raises_limit_exceeded_when_no_free_slot(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """With all slots occupied, create_browser raises BrowserLimitExceeded."""
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    # Fill every active sandbox with a fake browser row (no container).
    sandboxes = await sandbox_write_dao.find_active_without_browsers()
    for sb in sandboxes:
        await browser_write_dao.create(
            BrowserCreateParameters(
                container_id=f"fake-{sb.index}",
                network_id=sb.network_id,
                variant="camoufox",
                host="10.0.0.1",
                port=80,
                idle_ttl_seconds=60,
                created_at=datetime.now(UTC),
            )
        )
    cmd = CreateBrowserCommand(
        settings=service_settings,
        create_container=await service_request_container.get(CreateContainerCommand),
        start_container=await service_request_container.get(StartContainerCommand),
        inspect_container=await service_request_container.get(InspectContainerCommand),
        remove_container=await service_request_container.get(RemoveContainerCommand),
        sandbox_dao=sandbox_write_dao,
        browser_dao=browser_write_dao,
    )
    with pytest.raises(BrowserLimitExceeded):
        await cmd(CreateBrowserParameters(variant="camoufox", idle_ttl_seconds=60))

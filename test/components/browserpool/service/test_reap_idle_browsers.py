"""Integration tests for ReapIdleBrowsersCommand against a real Docker daemon.

ReapIdle force-removes every active browser whose idle deadline has passed and
marks its row inactive (the row is never deleted). An alpine container stands
in for the browser container; the row is inserted with an already-expired
`last_touched_at` so the find_expired query selects it immediately.
"""

from datetime import UTC, datetime, timedelta

import pytest
from browserpool.container_driver import RemoveContainerCommand
from browserpool.database import (
    BrowserCreateParameters,
    BrowserDAO,
    SandboxDAO,
    WriteSession,
)
from browserpool.service.commands.reap_idle_browsers import (
    ReapIdleBrowsersCommand,
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
async def test_reap_idle_removes_expired_browser_container_and_deactivates_row(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """An expired active browser is force-removed and its row deactivated."""
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    sandbox = (await sandbox_write_dao.find_active_without_browsers())[0]
    expired_at = datetime.now(UTC) - timedelta(hours=2)
    container_id = await make_alpine_container(
        service_request_container,
        service_settings,
        sandbox,
        f"reap-{sandbox.index}",
        extra_labels={
            service_settings.browser_variant_label: "camoufox",
            service_settings.browser_sandbox_network_id_label: sandbox.network_id,
            service_settings.browser_idle_ttl_seconds_label: "1",
            service_settings.browser_created_at_label: str(int(expired_at.timestamp())),
        },
    )
    await browser_write_dao.create(
        BrowserCreateParameters(
            container_id=container_id,
            network_id=sandbox.network_id,
            variant="camoufox",
            host="10.0.0.2",
            port=80,
            idle_ttl_seconds=1,
            last_touched_at=expired_at,
            created_at=expired_at,
        )
    )
    cmd = ReapIdleBrowsersCommand(
        browser_dao=browser_write_dao,
        remove_container=await service_request_container.get(RemoveContainerCommand),
    )
    reaped = await cmd()
    assert len(reaped) == 1
    assert reaped[0].container_id == container_id
    found = await browser_write_dao.find_by_id(container_id)
    assert found is not None and found.active is False


@pytest.mark.asyncio
async def test_reaped_sandboxes_are_reused_by_next_create(
    monkeypatch: pytest.MonkeyPatch,
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    browser_write_dao: BrowserDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """Sandboxes whose browsers were reaped are free for new browsers."""
    patch_camoufox_to_alpine_listener(monkeypatch)
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    created = [
        await create_browser(
            service_request_container,
            service_settings,
            sandbox_write_dao,
            browser_write_dao,
        )
        for _ in range(service_settings.browser_limit)
    ]
    expired_at = datetime.now(UTC) - timedelta(hours=2)
    for browser in created:
        row = await browser_write_dao.find_by_id(browser.container_id)
        assert row is not None
        row.last_touched_at = expired_at
        await browser_write_dao.save(row)

    reap = ReapIdleBrowsersCommand(
        browser_dao=browser_write_dao,
        remove_container=await service_request_container.get(RemoveContainerCommand),
    )
    assert len(await reap()) == len(created)

    replacement = await create_browser(
        service_request_container,
        service_settings,
        sandbox_write_dao,
        browser_write_dao,
    )
    assert replacement.container_id not in {b.container_id for b in created}

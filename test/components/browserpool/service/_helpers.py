from datetime import UTC, datetime
from typing import Any

import pytest
from browserpool.container_driver import (
    ConnectNetworkCommand,
    CreateContainerCommand,
    CreateNetworkCommand,
    InspectContainerCommand,
    ListNetworksCommand,
    RemoveContainerCommand,
    StartContainerCommand,
    StartContainerParameters,
)
from browserpool.container_driver.dto.container import (
    ContainerConfig,
    EndpointConfig,
    NetworkingConfig,
)
from browserpool.database import (
    BrowserCreateParameters,
    BrowserDAO,
    SandboxDAO,
    WriteSession,
)
from browserpool.database.models.sandbox import Sandbox
from browserpool.service.commands.create_browser import (
    CreateBrowserCommand,
    CreateBrowserParameters,
)
from browserpool.service.commands.reconcile_sandboxes import (
    ReconcileSandboxesCommand,
)
from browserpool.service.dto import Browser
from browserpool.service.settings import ServiceSettings
from browserpool.variant.camoufox import (
    _settings as camoufox_settings,  # pyright: ignore[reportPrivateUsage]
)
from dishka import AsyncContainer


def patch_camoufox_to_alpine_listener(
    monkeypatch: pytest.MonkeyPatch,
    port: int = 9222,
) -> None:
    """Make the camoufox variant run an alpine image that listens on `port`.

    The real camoufox image is large and pulls slowly. For integration tests we
    only need the readiness TCP probe to succeed, so we point the variant at
    `alpine:3.20` running a busybox `nc` loop on `port`.
    """
    object.__setattr__(camoufox_settings, "camoufox_playwright_port", port)
    object.__setattr__(camoufox_settings, "camoufox_image_name", "alpine")
    object.__setattr__(camoufox_settings, "camoufox_image_tag", "3.20")

    from browserpool.variant import CamoufoxBrowser

    @property
    def container_config(self: Any) -> ContainerConfig:
        return ContainerConfig(
            image="alpine:3.20",
            name=self._container_name,
            detach=True,
            command=[
                "sh",
                "-c",
                f"while true; do nc -l -p {port}; done",
            ],
            labels=self._labels,
            networking_config=NetworkingConfig(
                endpoints_config={self._network_name: EndpointConfig()}
            ),
        )

    monkeypatch.setattr(CamoufoxBrowser, "container_config", container_config)


async def build_reconcile_sandboxes(
    request_container: AsyncContainer,
    settings: ServiceSettings,
    sandbox_dao: SandboxDAO[WriteSession],
) -> ReconcileSandboxesCommand:
    """Wire a ReconcileSandboxesCommand from the request container."""
    return ReconcileSandboxesCommand(
        settings=settings,
        sandbox_dao=sandbox_dao,
        list_networks=await request_container.get(ListNetworksCommand),
        create_network=await request_container.get(CreateNetworkCommand),
        inspect_container=await request_container.get(InspectContainerCommand),
        connect_network=await request_container.get(ConnectNetworkCommand),
    )


async def provision_sandboxes(
    request_container: AsyncContainer,
    settings: ServiceSettings,
    sandbox_dao: SandboxDAO[WriteSession],
) -> None:
    """Run reconcile_sandboxes once so all browser_limit slots exist."""
    cmd = await build_reconcile_sandboxes(request_container, settings, sandbox_dao)
    await cmd()


async def create_browser(
    request_container: AsyncContainer,
    settings: ServiceSettings,
    sandbox_dao: SandboxDAO[WriteSession],
    browser_dao: BrowserDAO[WriteSession],
    variant: str = "camoufox",
    idle_ttl_seconds: int = 60,
) -> Browser:
    """Wire and run CreateBrowserCommand, returning the created browser."""
    cmd = CreateBrowserCommand(
        settings=settings,
        create_container=await request_container.get(CreateContainerCommand),
        start_container=await request_container.get(StartContainerCommand),
        inspect_container=await request_container.get(InspectContainerCommand),
        remove_container=await request_container.get(RemoveContainerCommand),
        sandbox_dao=sandbox_dao,
        browser_dao=browser_dao,
    )
    return await cmd(
        CreateBrowserParameters(variant=variant, idle_ttl_seconds=idle_ttl_seconds)
    )


async def make_alpine_container(
    request_container: AsyncContainer,
    settings: ServiceSettings,
    sandbox: Sandbox,
    name: str,
    extra_labels: dict[str, str] | None = None,
) -> str:
    """Create and start an alpine container attached to a sandbox network.

    Used as a stand-in for a browser container that does not need to pass a
    readiness probe (orphan/reap scenarios): `sleep infinity` keeps it alive.
    """
    labels = {settings.managed_label: "true"}
    if extra_labels:
        labels.update(extra_labels)
    create_container = await request_container.get(CreateContainerCommand)
    start_container = await request_container.get(StartContainerCommand)
    response = await create_container(
        ContainerConfig(
            image="alpine:3.20",
            name=name,
            detach=True,
            command=["sleep", "infinity"],
            labels=labels,
            networking_config=NetworkingConfig(
                endpoints_config={sandbox.network_name: EndpointConfig()}
            ),
        )
    )
    await start_container(StartContainerParameters(container_id=response.container_id))
    return response.container_id


async def seed_browser(
    request_container: AsyncContainer,
    settings: ServiceSettings,
    *,
    container_id: str,
    active: bool = True,
    last_touched_at: datetime | None = None,
    network_id: str | None = None,
) -> str:
    """Provision sandboxes if needed and insert a browser row without Docker.

    Returns the sandbox network id the browser was attached to.
    """
    sandbox_dao = await request_container.get(SandboxDAO[WriteSession])
    browser_dao = await request_container.get(BrowserDAO[WriteSession])
    if network_id is not None:
        sandbox = await sandbox_dao.find_by_id(network_id)
        if sandbox is None:
            raise ValueError(f"Unknown sandbox network id: {network_id}")
    else:
        sandboxes = await sandbox_dao.find_active_without_browsers()
        if not sandboxes:
            await provision_sandboxes(request_container, settings, sandbox_dao)
            sandboxes = await sandbox_dao.find_active_without_browsers()
        sandbox = sandboxes[0]
    await browser_dao.create(
        BrowserCreateParameters(
            container_id=container_id,
            network_id=sandbox.network_id,
            variant="camoufox",
            host="10.0.0.2",
            port=9222,
            idle_ttl_seconds=60,
            last_touched_at=last_touched_at or datetime.now(UTC),
            active=active,
        )
    )
    return sandbox.network_id

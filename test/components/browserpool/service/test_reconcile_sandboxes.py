"""Integration tests for ReconcileSandboxesCommand against a real Docker daemon.

Reconcile synchronizes managed sandbox networks between Docker and the
database: it creates missing networks up to browser_limit, deactivates rows
whose network vanished, and adopts managed networks that exist in Docker but
have no database row yet.
"""

import pytest
from browserpool.container_driver import (
    CreateNetworkCommand,
    LabelFilters,
    ListNetworksCommand,
    NetworkConfig,
    RemoveNetworkCommand,
    RemoveNetworkParameters,
)
from browserpool.container_driver.client import DockerClient
from browserpool.database import SandboxDAO, WriteSession
from browserpool.service.commands.reconcile_sandboxes import (
    ReconcileSandboxesCommand,
)
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer

from ._helpers import build_reconcile_sandboxes, provision_sandboxes


@pytest.mark.asyncio
async def test_reconcile_creates_networks_up_to_limit(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """A fresh reconcile creates browser_limit managed networks and rows."""
    limit = service_settings.browser_limit
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    list_networks = await service_request_container.get(ListNetworksCommand)
    networks = await list_networks(
        LabelFilters(labels={service_settings.managed_label: "true"})
    )
    names = {n.name for n in networks}
    for i in range(limit):
        assert f"{service_settings.browser_slot_network_prefix}-{i}" in names
    rows = await sandbox_write_dao.find_active()
    assert len(rows) == limit
    assert {r.index for r in rows} == set(range(limit))


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    service_request_container: AsyncContainer,
) -> None:
    """A second reconcile on a populated pool creates nothing new."""
    cmd = await build_reconcile_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    first: ReconcileSandboxesCommand = cmd
    first_result = await first()
    second_result = await first()
    assert len(first_result.created) == service_settings.browser_limit
    assert second_result.created == []
    assert second_result.adopted == []
    assert second_result.reactivated == []
    assert second_result.deactivated == []


@pytest.mark.asyncio
async def test_reconcile_deactivates_row_when_network_vanishes(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    docker_client: DockerClient,
    service_request_container: AsyncContainer,
) -> None:
    """If a managed network is removed, reconcile marks its row inactive."""
    await provision_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    rows = await sandbox_write_dao.find_active()
    target = rows[0]
    remove_network = RemoveNetworkCommand(docker_client)
    await remove_network(RemoveNetworkParameters(id=target.network_id))
    cmd = await build_reconcile_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    result = await cmd()
    assert any(s.network_id == target.network_id for s in result.deactivated)
    rows_after = await sandbox_write_dao.find_active()
    assert len(rows_after) == service_settings.browser_limit


@pytest.mark.asyncio
async def test_reconcile_adopts_existing_managed_network_without_row(
    service_settings: ServiceSettings,
    sandbox_write_dao: SandboxDAO[WriteSession],
    docker_client: DockerClient,
    service_request_container: AsyncContainer,
) -> None:
    """A managed network with the index label but no DB row is adopted."""
    create_network = CreateNetworkCommand(docker_client)
    net_name = f"{service_settings.browser_slot_network_prefix}-0"
    net_response = await create_network(
        NetworkConfig(
            name=net_name,
            driver="bridge",
            labels={
                service_settings.managed_label: "true",
                service_settings.sandbox_index_label: "0",
            },
        )
    )
    cmd = await build_reconcile_sandboxes(
        service_request_container, service_settings, sandbox_write_dao
    )
    result = await cmd()
    adopted_ids = {s.network_id for s in result.adopted}
    assert net_response.network_id in adopted_ids
    row = await sandbox_write_dao.find_active_by_index(0)
    assert row is not None and row.network_id == net_response.network_id

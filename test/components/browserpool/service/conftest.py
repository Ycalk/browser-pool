"""Fixtures for service-component integration tests.

These tests talk to the real Docker daemon and the real SQLite database
(the same browserpool.db used by the database tests). They create managed
sandbox networks and nginx containers on demand and clean everything
carrying the managed label/prefix up at teardown, so repeated runs stay
idempotent.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from browserpool.container_driver import (
    ContainerDriverProvider,
    LabelFilters,
    ListContainersCommand,
    ListContainersParameters,
    ListNetworksCommand,
    RemoveContainerCommand,
    RemoveContainerParameters,
    RemoveNetworkCommand,
    RemoveNetworkParameters,
)
from browserpool.container_driver.client import DockerClient
from browserpool.database import BrowserDAO, ReadSession, SandboxDAO, WriteSession
from browserpool.service.settings import ServiceSettings
from dishka import AsyncContainer, make_async_container


@pytest_asyncio.fixture(scope="session")
async def service_app_container() -> AsyncIterator[AsyncContainer]:
    """App-scoped container exposing Docker, Database and Service providers."""
    from browserpool.database import DatabaseProvider
    from browserpool.service.core import ServiceProvider

    container = make_async_container(
        ContainerDriverProvider(), DatabaseProvider(), ServiceProvider()
    )
    try:
        yield container
    finally:
        await container.close()


@pytest_asyncio.fixture
async def service_request_container(
    service_app_container: AsyncContainer,
) -> AsyncIterator[AsyncContainer]:
    async with service_app_container() as request_container:
        yield request_container


@pytest_asyncio.fixture(scope="session")
async def docker_client(
    service_app_container: AsyncContainer,
) -> DockerClient:
    return await service_app_container.get(DockerClient)


@pytest_asyncio.fixture
async def service_settings(
    service_app_container: AsyncContainer,
) -> ServiceSettings:
    return await service_app_container.get(ServiceSettings)


@pytest_asyncio.fixture
async def sandbox_write_dao(
    service_request_container: AsyncContainer,
) -> SandboxDAO[WriteSession]:
    return await service_request_container.get(SandboxDAO[WriteSession])


@pytest_asyncio.fixture
async def browser_write_dao(
    service_request_container: AsyncContainer,
) -> BrowserDAO[WriteSession]:
    return await service_request_container.get(BrowserDAO[WriteSession])


@pytest_asyncio.fixture
async def sandbox_read_dao(
    service_app_container: AsyncContainer,
) -> AsyncIterator[SandboxDAO[ReadSession]]:
    """A read-session sandbox DAO in its own request scope (separate from the
    write scope), so ReconcileBrowsersCommand can be wired with a ReadSession
    while the write scope stays open."""
    async with service_app_container() as request_container:
        yield await request_container.get(SandboxDAO[ReadSession])


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_managed_docker(
    docker_client: DockerClient,
) -> AsyncIterator[None]:
    """Remove managed networks/containers created by any test, after each test."""
    yield
    await _purge_managed_docker(docker_client)


async def _purge_managed_docker(docker_client: DockerClient) -> None:
    list_containers = ListContainersCommand(docker_client)
    remove_container = RemoveContainerCommand(docker_client)
    list_networks = ListNetworksCommand(docker_client)
    remove_network = RemoveNetworkCommand(docker_client)

    containers = await list_containers(
        ListContainersParameters(
            all=True,
            filters=LabelFilters(labels={"browserpool.managed": "true"}),
        )
    )
    for container in containers:
        try:
            await remove_container(
                RemoveContainerParameters(id=container.id, force=True)
            )
        except Exception:
            pass

    networks = await list_networks(LabelFilters(labels={"browserpool.managed": "true"}))
    for network in networks:
        try:
            await remove_network(RemoveNetworkParameters(id=network.id))
        except Exception:
            pass

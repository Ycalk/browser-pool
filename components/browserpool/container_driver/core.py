from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource
from httpx import AsyncClient, AsyncHTTPTransport
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from .client import DockerClient
from .commands import (
    CreateContainerCommand,
    RemoveContainerCommand,
    StartContainerCommand,
    StopContainerCommand,
)
from .settings import ContainerDriverSettings
from .version import ensure_api_version


class ContainerDriverProvider(Provider):
    commands: CompositeDependencySource = provide_all(
        CreateContainerCommand,
        RemoveContainerCommand,
        StartContainerCommand,
        StopContainerCommand,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.APP)
    def settings(self) -> ContainerDriverSettings:
        return ContainerDriverSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    async def docker_client(
        self,
        settings: ContainerDriverSettings,
    ) -> AsyncIterator[DockerClient]:
        async with AsyncClient(
            transport=AsyncHTTPTransport(uds=settings.docker_host),
            base_url=f"http://docker/{settings.docker_api_version}",
            timeout=settings.docker_timeout_seconds,
        ) as client:
            HTTPXClientInstrumentor.instrument_client(client)
            docker_client = DockerClient(client)
            await ensure_api_version(docker_client, settings)
            yield docker_client

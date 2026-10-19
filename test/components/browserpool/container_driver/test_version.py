import httpx
import pytest
from browserpool.container_driver import DockerFatalError
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.settings import ContainerDriverSettings
from browserpool.container_driver.version import ensure_api_version

_DAEMON = {"Version": "29.7.2", "ApiVersion": "1.55", "MinAPIVersion": "1.40"}


def _case(
    payload: dict[str, str], configured: str
) -> tuple[DockerClient, ContainerDriverSettings, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, json=payload)

    client = DockerClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=f"http://docker/{configured}",
        )
    )
    return client, ContainerDriverSettings(docker_api_version=configured), requested


@pytest.mark.asyncio
async def test_version_is_requested_without_api_prefix():
    client, settings, requested = _case(_DAEMON, "v1.55")

    version = await ensure_api_version(client, settings)

    assert requested == ["/version"]
    assert (version.version, version.api_version, version.min_api_version) == (
        "29.7.2",
        "1.55",
        "1.40",
    )


@pytest.mark.asyncio
async def test_fails_when_daemon_supports_less_than_configured():
    client, settings, _ = _case({**_DAEMON, "ApiVersion": "1.54"}, "v1.55")

    with pytest.raises(DockerFatalError):
        await ensure_api_version(client, settings)


@pytest.mark.asyncio
async def test_fails_when_configured_is_below_daemon_minimum():
    client, settings, _ = _case(_DAEMON, "1.30")

    with pytest.raises(DockerFatalError):
        await ensure_api_version(client, settings)

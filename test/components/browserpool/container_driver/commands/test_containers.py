import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from browserpool.container_driver import (
    DockerNotFoundException,
    InspectContainerCommand,
    InspectContainerParameters,
    LabelFilters,
    ListContainersCommand,
    ListContainersParameters,
)
from browserpool.container_driver.client import DockerClient

_LIST_PAYLOAD: list[dict[str, Any]] = [
    {
        "Id": "c-on-a",
        "Names": ["/browserpool-a"],
        "Image": "browserpool-chromium",
        "Created": 1780000000,
        "State": "running",
        "Status": "Up 5 seconds",
        "Labels": {"browserpool.managed": "true"},
        "Ports": [{"IP": "127.0.0.1", "PrivatePort": 9222, "PublicPort": 32771}],
        "NetworkSettings": {
            "Networks": {
                "browserpool-net-0": {
                    "NetworkID": "net-0",
                    "IPAddress": "10.100.0.2",
                    "Gateway": "10.100.0.1",
                }
            }
        },
    },
    {
        "Id": "c-on-b",
        "Names": ["/browserpool-b"],
        "Image": "browserpool-camoufox",
        "Created": 1780000001,
        "State": "created",
        "Status": "Created",
        "Labels": {},
        "Ports": [],
        "NetworkSettings": {
            "Networks": {
                "browserpool-net-1": {
                    "NetworkID": "net-1",
                    "IPAddress": "",
                    "Gateway": "10.101.0.1",
                }
            }
        },
    },
    {
        "Id": "c-on-bridge",
        "Names": ["/unrelated"],
        "Image": "alpine",
        "Created": 1780000002,
        "State": "running",
        "Status": "Up 1 second",
        "Labels": {},
        "Ports": [],
        "NetworkSettings": {
            "Networks": {
                "bridge": {"NetworkID": "bridge-id", "IPAddress": "172.17.0.6"}
            }
        },
    },
]

_DETAIL_PAYLOAD: dict[str, Any] = {
    "Id": "c-on-a",
    "Name": "/browserpool-a",
    "Image": "browserpool-chromium",
    "Created": "2026-09-15T20:20:12.433067573Z",
    "State": {
        "Status": "created",
        "Running": False,
        "ExitCode": 0,
        "StartedAt": "0001-01-01T00:00:00Z",
        "FinishedAt": "0001-01-01T00:00:00Z",
    },
    "Config": {
        "Labels": {"browserpool.managed": "true"},
        "Env": ["BROWSER_PROXY=http://user:pass@proxy.local:8000", "TZ=UTC"],
    },
    "NetworkSettings": {
        "Networks": {
            "browserpool-net-0": {
                "NetworkID": "net-0",
                "IPAddress": "10.100.0.2",
                "Gateway": "10.100.0.1",
            }
        }
    },
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DockerClient:
    return DockerClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://docker/v1.55"
        )
    )


@pytest.mark.asyncio
async def test_list_returns_containers_from_every_network():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["all"] = request.url.params["all"]
        seen["filters"] = request.url.params["filters"]
        return httpx.Response(200, json=_LIST_PAYLOAD)

    command = ListContainersCommand(_client(handler))
    containers = await command(ListContainersParameters())

    assert seen["path"] == "/v1.55/containers/json"
    assert seen["all"] == "true"
    assert json.loads(seen["filters"]) == {}
    assert [container.name for container in containers] == [
        "browserpool-a",
        "browserpool-b",
        "unrelated",
    ]
    assert {
        name: network.ip_address
        for container in containers
        for name, network in container.networks.items()
    } == {
        "browserpool-net-0": "10.100.0.2",
        "browserpool-net-1": "",
        "bridge": "172.17.0.6",
    }


@pytest.mark.asyncio
async def test_list_forwards_labels_as_filter_document():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["filters"] = request.url.params["filters"]
        return httpx.Response(200, json=[])

    command = ListContainersCommand(_client(handler))
    await command(
        ListContainersParameters(
            filters=LabelFilters(labels={"browserpool.managed": "true"})
        )
    )

    assert json.loads(seen["filters"]) == {"label": ["browserpool.managed=true"]}


@pytest.mark.asyncio
async def test_inspect_parses_environment_networks_and_unset_times():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=_DETAIL_PAYLOAD)

    command = InspectContainerCommand(_client(handler))
    container = await command(InspectContainerParameters(id="browserpool-a"))

    assert seen["path"] == "/v1.55/containers/browserpool-a/json"
    assert container.name == "browserpool-a"
    assert container.state.status == "created"
    assert container.state.started_at is None
    assert container.state.finished_at is None
    assert (
        container.environment["BROWSER_PROXY"] == "http://user:pass@proxy.local:8000"
    )
    assert container.labels == {"browserpool.managed": "true"}
    assert container.networks["browserpool-net-0"].ip_address == "10.100.0.2"


@pytest.mark.asyncio
async def test_inspect_of_missing_container_raises_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "No such container: browserpool-x"})

    command = InspectContainerCommand(_client(handler))

    with pytest.raises(DockerNotFoundException):
        await command(InspectContainerParameters(id="browserpool-x"))


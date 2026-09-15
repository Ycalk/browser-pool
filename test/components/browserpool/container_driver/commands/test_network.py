import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from browserpool.container_driver import (
    CreateNetworkCommand,
    DockerForbiddenException,
    LabelFilters,
    ListNetworksCommand,
    NetworkConfig,
    NetworkIPAM,
    NetworkIPAMConfig,
    NetworkOptions,
    PruneNetworksCommand,
    RemoveNetworkCommand,
    RemoveNetworkParameters,
)
from browserpool.container_driver.client import DockerClient

_NETWORK: dict[str, Any] = {
    "Id": "net-1",
    "Name": "browserpool-1",
    "Driver": "bridge",
    "Internal": False,
    "Labels": {"browserpool.managed": "true"},
    "Options": {"com.docker.network.bridge.enable_icc": "false"},
    "IPAM": {"Driver": "default", "Config": [{"Subnet": "10.100.1.0/24"}]},
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DockerClient:
    return DockerClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://docker/v1.55"
        )
    )


@pytest.mark.asyncio
async def test_create_sends_wire_aliases_and_icc_option():
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(201, json={"Id": "net-1", "Warning": ""})

    command = CreateNetworkCommand(_client(handler))
    response = await command(
        NetworkConfig(
            name="browserpool-1",
            driver="bridge",
            labels={"browserpool.managed": "true"},
            options=NetworkOptions(enable_icc=False),
            ipam=NetworkIPAM(
                driver="default",
                config=[NetworkIPAMConfig(subnet="10.100.1.0/24")],
            ),
        )
    )

    assert response.network_id == "net-1"
    assert sent["Name"] == "browserpool-1"
    assert sent["Options"] == {"com.docker.network.bridge.enable_icc": "false"}
    assert sent["Labels"] == {"browserpool.managed": "true"}
    assert sent["IPAM"]["Config"][0]["Subnet"] == "10.100.1.0/24"


@pytest.mark.asyncio
async def test_list_sends_labels_as_docker_filter_document():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["filters"] = request.url.params["filters"]
        return httpx.Response(200, json=[_NETWORK])

    command = ListNetworksCommand(_client(handler))
    networks = await command(LabelFilters(labels={"browserpool.managed": "true"}))

    assert seen["path"] == "/v1.55/networks"
    assert json.loads(seen["filters"]) == {"label": ["browserpool.managed=true"]}
    assert [network.name for network in networks] == ["browserpool-1"]
    assert networks[0].ipam is not None
    assert networks[0].ipam.config[0].subnet == "10.100.1.0/24"


@pytest.mark.asyncio
async def test_prune_returns_deleted_names():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["filters"] = request.url.params["filters"]
        return httpx.Response(200, json={"NetworksDeleted": ["browserpool-1"]})

    command = PruneNetworksCommand(_client(handler))
    response = await command(LabelFilters(labels={"browserpool.managed": "true"}))

    assert seen["path"] == "/v1.55/networks/prune"
    assert json.loads(seen["filters"]) == {"label": ["browserpool.managed=true"]}
    assert response.networks_deleted == ["browserpool-1"]


@pytest.mark.asyncio
async def test_prune_accepts_null_when_nothing_was_deleted():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"NetworksDeleted": None})

    command = PruneNetworksCommand(_client(handler))
    response = await command(LabelFilters(labels={"browserpool.managed": "true"}))

    assert response.networks_deleted == []


@pytest.mark.asyncio
async def test_remove_translates_network_in_use_to_forbidden():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"message": "network browserpool-1 has active endpoints"}
        )

    command = RemoveNetworkCommand(_client(handler))

    with pytest.raises(DockerForbiddenException):
        await command(RemoveNetworkParameters(id="browserpool-1"))

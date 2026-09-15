import json
from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import NetworkFilters, NetworkResponse
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import TypeAdapter

from .exceptions import DockerFatalError

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)
_adapter: Final[TypeAdapter[list[NetworkResponse]]] = TypeAdapter(
    list[NetworkResponse]
)


class ListNetworksCommand(Command[NetworkFilters, list[NetworkResponse]]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: NetworkFilters) -> list[NetworkResponse]:
        with _tracer.start_as_current_span("container_driver.list_networks") as span:
            path = "/networks"
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            query_params: dict[str, str] = {
                "filters": json.dumps(
                    parameters.model_dump(by_alias=True, exclude_none=True)
                )
            }
            _logger.info(
                "calling_docker",
                method="GET",
                path=path,
                query_params=json.dumps(query_params),
            )
            response = await self._client.get(path, params=query_params)
            if response.status_code == 200:
                networks = _adapter.validate_json(response.content)
                span.set_attribute("response.networks.count", len(networks))
                _logger.info("successful_response", count=len(networks))
                return networks

            try:
                response.raise_for_status()
            except HTTPStatusError as e:
                message = response.text.strip()
                try:
                    message = response.json()["message"]
                except Exception:
                    pass
                raise DockerFatalError(message) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

import json
from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import ContainerSummaryResponse, LabelFilters
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel, Field, TypeAdapter

from .exceptions import DockerFatalError

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)
_adapter: Final[TypeAdapter[list[ContainerSummaryResponse]]] = TypeAdapter(
    list[ContainerSummaryResponse]
)


class ListContainersParameters(BaseModel):
    all: bool = True
    filters: LabelFilters = Field(default_factory=LabelFilters)


class ListContainersCommand(
    Command[ListContainersParameters, list[ContainerSummaryResponse]]
):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(
        self, parameters: ListContainersParameters
    ) -> list[ContainerSummaryResponse]:
        with _tracer.start_as_current_span("container_driver.list_containers") as span:
            path = "/containers/json"
            span.set_attribute("request.docker.path", path)
            span.set_attribute("request.all", parameters.all)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            # No network filter: containers attached to any network are returned.
            query_params: dict[str, str | bool] = {
                "all": parameters.all,
                "filters": parameters.filters.as_query(),
            }
            _logger.info(
                "calling_docker",
                method="GET",
                path=path,
                query_params=json.dumps(query_params),
            )
            response = await self._client.get(path, params=query_params)
            if response.status_code == 200:
                containers = _adapter.validate_json(response.content)
                span.set_attribute("response.containers.count", len(containers))
                _logger.info("successful_response", count=len(containers))
                return containers

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

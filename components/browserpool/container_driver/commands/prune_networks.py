import json
from typing import Annotated, Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import LabelFilters
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel, BeforeValidator, Field

from .exceptions import DockerFatalError

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class PruneNetworksResponse(BaseModel):
    # Docker answers `NetworksDeleted: null` when there was nothing to prune.
    networks_deleted: Annotated[
        list[str],
        BeforeValidator(lambda value: [] if value is None else value),
        Field(validation_alias="NetworksDeleted"),
    ] = []


class PruneNetworksCommand(Command[LabelFilters, PruneNetworksResponse]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: LabelFilters) -> PruneNetworksResponse:
        with _tracer.start_as_current_span("container_driver.prune_networks") as span:
            path = "/networks/prune"
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            query_params: dict[str, str] = {
                "filters": json.dumps(
                    parameters.model_dump(by_alias=True, exclude_none=True)
                )
            }
            _logger.info(
                "calling_docker",
                method="POST",
                path=path,
                query_params=json.dumps(query_params),
            )
            response = await self._client.post(path, params=query_params)
            if response.status_code == 200:
                response_data = PruneNetworksResponse.model_validate_json(
                    response.content
                )
                span.set_attribute(
                    "response.networks.deleted", response_data.networks_deleted
                )
                _logger.info("successful_response", data=response_data)
                return response_data

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

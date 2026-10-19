from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import NetworkConfig
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel, Field

from .exceptions import (
    DockerBadRequestException,
    DockerConflictException,
    DockerFatalError,
    DockerForbiddenException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class CreateNetworkResponse(BaseModel):
    network_id: str = Field(validation_alias="Id")
    warning: str = Field(validation_alias="Warning", default="")


class CreateNetworkCommand(Command[NetworkConfig, CreateNetworkResponse]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: NetworkConfig) -> CreateNetworkResponse:
        with _tracer.start_as_current_span("container_driver.create_network") as span:
            path = "/networks/create"
            span.set_attribute("request.network.name", parameters.name)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            body = parameters.model_dump(by_alias=True, exclude_none=True)
            _logger.info(
                "calling_docker",
                method="POST",
                path=path,
                json=parameters.model_dump_json(by_alias=True, exclude_none=True),
            )
            response = await self._client.post(path, json=body)
            if response.status_code == 201:
                response_data = CreateNetworkResponse.model_validate_json(
                    response.content
                )
                span.set_attribute("response.network.id", response_data.network_id)
                _logger.info("successful_response", data=response_data)
                if response_data.warning != "":
                    _logger.warning("docker_warnings", warnings=response_data.warning)
                return response_data

            try:
                response.raise_for_status()
            except HTTPStatusError as e:
                message = response.text.strip()
                try:
                    message = response.json()["message"]
                except Exception:
                    pass
                raise {
                    400: DockerBadRequestException(message),
                    403: DockerForbiddenException(message),
                    409: DockerConflictException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

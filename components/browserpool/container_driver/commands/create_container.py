import json
from typing import Annotated, Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import ContainerConfig
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel, Field

from .exceptions import (
    DockerBadRequestException,
    DockerConflictException,
    DockerFatalError,
    DockerNotFoundException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class CreateContainerResponse(BaseModel):
    id: Annotated[str, Field(validation_alias="Id")]
    warnings: Annotated[list[str], Field(validation_alias="Warnings")] = []


class CreateContainerCommand(Command[ContainerConfig, CreateContainerResponse]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: ContainerConfig) -> CreateContainerResponse:
        with _tracer.start_as_current_span("container_driver.create_container") as span:
            path = "/containers/create"
            span.set_attribute("request.container.image", parameters.image)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            query_params: dict[str, str | None] = {
                "name": parameters.name,
            }
            if parameters.platform is not None:
                query_params["platform"] = parameters.platform
            json_data = parameters.model_dump_json(by_alias=True)
            _logger.info(
                "calling_docker",
                method="POST",
                path=path,
                query_params=json.dumps(query_params),
                json=json_data,
            )
            response = await self._client.post(
                path, params=query_params, json=json_data
            )
            if response.status_code == 201:
                response_data = CreateContainerResponse.model_validate_json(
                    response.content
                )
                span.set_attribute("response.container.id", response_data.id)
                span.set_attribute("response.warnings", response_data.warnings)
                _logger.info("successful_response", data=response_data)
                if len(response_data.warnings) > 0:
                    _logger.warning("docker_warnings", warnings=response_data.warnings)
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
                    404: DockerNotFoundException(message),
                    409: DockerConflictException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

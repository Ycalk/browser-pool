from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import ContainerDetailResponse
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel

from .exceptions import DockerFatalError, DockerNotFoundException

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class InspectContainerParameters(BaseModel):
    id: str


class InspectContainerCommand(
    Command[InspectContainerParameters, ContainerDetailResponse]
):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(
        self, parameters: InspectContainerParameters
    ) -> ContainerDetailResponse:
        with _tracer.start_as_current_span(
            "container_driver.inspect_container"
        ) as span:
            path = f"/containers/{parameters.id}/json"
            span.set_attribute("request.container.id", parameters.id)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            _logger.info("calling_docker", method="GET", path=path)
            response = await self._client.get(path)
            if response.status_code == 200:
                response_data = ContainerDetailResponse.model_validate_json(
                    response.content
                )
                span.set_attribute("response.container.id", response_data.id)
                span.set_attribute(
                    "response.container.state", response_data.state.status
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
                raise {
                    404: DockerNotFoundException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

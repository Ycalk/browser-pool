from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel

from .exceptions import (
    DockerFatalError,
    DockerForbiddenException,
    DockerNotFoundException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class RemoveNetworkParameters(BaseModel):
    id: str


class RemoveNetworkCommand(Command[RemoveNetworkParameters, None]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: RemoveNetworkParameters) -> None:
        with _tracer.start_as_current_span("container_driver.remove_network") as span:
            path = f"/networks/{parameters.id}"
            span.set_attribute("request.network.id", parameters.id)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            _logger.info("calling_docker", method="DELETE", path=path)
            response = await self._client.delete(path)
            if response.status_code == 204:
                return

            try:
                response.raise_for_status()
            except HTTPStatusError as e:
                message = response.text.strip()
                try:
                    message = response.json()["message"]
                except Exception:
                    pass
                raise {
                    403: DockerForbiddenException(message),
                    404: DockerNotFoundException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

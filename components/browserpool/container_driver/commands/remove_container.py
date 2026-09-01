import json
from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel

from .exceptions import (
    DockerBadRequestException,
    DockerConflictException,
    DockerFatalError,
    DockerNotFoundException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class RemoveContainerParameters(BaseModel):
    id: str
    remove_volumes: bool = False
    force: bool = False
    remove_link: bool = False


class RemoveContainerCommand(Command[RemoveContainerParameters, None]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: RemoveContainerParameters) -> None:
        with _tracer.start_as_current_span("container_driver.remove_container") as span:
            path = f"/containers/{parameters.id}"
            span.set_attribute("request.container.id", parameters.id)
            span.set_attribute("request.remove_volumes", parameters.remove_volumes)
            span.set_attribute("request.force", parameters.force)
            span.set_attribute("request.remove_link", parameters.remove_link)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            query_params: dict[str, str | int | None] = {
                "v": parameters.remove_volumes,
                "force": parameters.force,
                "link": parameters.remove_link,
            }
            _logger.info(
                "calling_docker",
                method="DELETE",
                path=path,
                query_params=json.dumps(query_params),
            )
            response = await self._client.delete(path, params=query_params)
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
                    400: DockerBadRequestException(message),
                    404: DockerNotFoundException(message),
                    409: DockerConflictException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

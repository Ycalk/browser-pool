import json
from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel

from .exceptions import (
    DockerFatalError,
    DockerNotFoundException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class StopContainerParameters(BaseModel):
    id: str
    signal: str | None = None
    timeout: int = 10


class StopContainerCommand(Command[StopContainerParameters, None]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: StopContainerParameters) -> None:
        with _tracer.start_as_current_span("container_driver.stop_container") as span:
            path = f"/containers/{parameters.id}/stop"
            span.set_attribute("request.container.id", parameters.id)
            span.set_attribute("request.signal", parameters.signal or "default")
            span.set_attribute("request.timeout", parameters.timeout)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            query_params: dict[str, str | int | None] = {
                "signal": parameters.signal,
                "t": parameters.timeout,
            }
            _logger.info(
                "calling_docker",
                method="POST",
                path=path,
                query_params=json.dumps(query_params),
            )
            response = await self._client.post(path, params=query_params)
            if response.status_code in (204, 304):
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
                    404: DockerNotFoundException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

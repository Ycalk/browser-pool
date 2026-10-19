from typing import Final, override

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import EndpointConfig, NetworkConnectConfig
from browserpool.domain_core import Command
from httpx import HTTPStatusError
from opentelemetry import trace
from pydantic import BaseModel

from .exceptions import (
    DockerBadRequestException,
    DockerFatalError,
    DockerForbiddenException,
    DockerNotFoundException,
)

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ConnectNetworkParameters(BaseModel):
    network_id: str
    container_id: str
    endpoint_config: EndpointConfig | None = None


class ConnectNetworkCommand(Command[ConnectNetworkParameters, None]):
    def __init__(self, client: DockerClient) -> None:
        self._client: DockerClient = client

    @override
    async def __call__(self, parameters: ConnectNetworkParameters) -> None:
        with _tracer.start_as_current_span("container_driver.connect_network") as span:
            path = f"/networks/{parameters.network_id}/connect"
            body = NetworkConnectConfig(
                container=parameters.container_id,
                endpoint_config=parameters.endpoint_config,
            )
            span.set_attribute("request.network.id", parameters.network_id)
            span.set_attribute("request.container.id", parameters.container_id)
            span.set_attribute("request.docker.path", path)
            _logger.info("parameters", parameters=parameters.model_dump_json())

            _logger.info(
                "calling_docker",
                method="POST",
                path=path,
                json=body.model_dump_json(by_alias=True, exclude_none=True),
            )
            response = await self._client.post(
                path, json=body.model_dump(by_alias=True, exclude_none=True)
            )
            if response.status_code in (200, 204):
                _logger.info("successful_response", network_id=parameters.network_id)
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
                    403: DockerForbiddenException(message),
                    404: DockerNotFoundException(message),
                }.get(response.status_code, DockerFatalError(message)) from e

            raise DockerFatalError(f"Unexpected status code: {response.status_code}")

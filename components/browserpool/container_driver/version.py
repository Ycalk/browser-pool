from typing import Final

import structlog
from browserpool.container_driver.client import DockerClient
from browserpool.container_driver.dto import DockerVersionResponse
from browserpool.container_driver.settings import ContainerDriverSettings
from opentelemetry import trace

from .commands.exceptions import DockerFatalError

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


def _parse_api_version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.removeprefix("v").split("."))
    except ValueError as e:
        raise DockerFatalError(f"Unparsable Docker API version: {value!r}") from e


def _validate_api_version(*, configured: str, supported: str, minimum: str) -> None:
    configured_api = _parse_api_version(configured)
    if _parse_api_version(supported) < configured_api:
        raise DockerFatalError(
            f"docker_api_version={configured} is above the daemon max {supported}"
        )
    if configured_api < _parse_api_version(minimum):
        raise DockerFatalError(
            f"docker_api_version={configured} is below the daemon min {minimum}"
        )


async def ensure_api_version(
    client: DockerClient, settings: ContainerDriverSettings
) -> DockerVersionResponse:
    """Fail fast when the daemon does not support the configured API version."""
    with _tracer.start_as_current_span("container_driver.check_version") as span:
        path = "/version"
        # Unversioned on purpose: the configured /v<api> prefix is rejected by a daemon
        # that does not support it, which is the mismatch being checked.
        url = client.base_url.copy_with(path=path)
        configured = settings.docker_api_version
        span.set_attribute("request.docker.path", path)
        span.set_attribute("request.docker.api_version", configured)
        _logger.info(
            "calling_docker",
            method="GET",
            path=path,
            configured_api_version=configured,
        )

        response = await client.get(url)
        if response.status_code != 200:
            message = response.text.strip()
            try:
                message = response.json()["message"]
            except Exception:
                pass
            raise DockerFatalError(message)

        version = DockerVersionResponse.model_validate_json(response.content)
        span.set_attribute("response.docker.version", version.version)
        span.set_attribute("response.docker.api_version", version.api_version)
        span.set_attribute("response.docker.min_api_version", version.min_api_version)
        _logger.info("successful_response", data=version)

        _validate_api_version(
            configured=configured,
            supported=version.api_version,
            minimum=version.min_api_version,
        )

        return version

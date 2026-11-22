from typing import Final, override

import structlog
from browserpool.container_driver import (
    DockerNotFoundException,
    RemoveContainerCommand,
    RemoveContainerParameters,
)
from browserpool.database import BrowserDAO, BrowserLoadEnum, WriteSession
from browserpool.domain_core import Command
from browserpool.service.dto import Browser
from browserpool.service.exceptions import BrowserNotFound
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class RemoveBrowserParameters(BaseModel):
    container_id: str


class RemoveBrowserCommand(Command[RemoveBrowserParameters, Browser]):
    """Remove a browser container and deactivate its lease."""

    def __init__(
        self,
        browser_dao: BrowserDAO[WriteSession],
        remove_container: RemoveContainerCommand,
    ) -> None:
        self._browser_dao: BrowserDAO[WriteSession] = browser_dao
        self._remove_container: RemoveContainerCommand = remove_container

    @override
    async def __call__(self, parameters: RemoveBrowserParameters) -> Browser:
        with _tracer.start_as_current_span("service.remove_browser") as span:
            span.set_attribute("request.container.id", parameters.container_id)
            model = await self._browser_dao.find_by_id(
                parameters.container_id, includes=[BrowserLoadEnum.SANDBOX]
            )
            if model is None:
                raise BrowserNotFound(f"Browser {parameters.container_id} is not found")
            if not model.active:
                return Browser.from_persistence(model)
            try:
                await self._remove_container(
                    RemoveContainerParameters(id=parameters.container_id, force=True)
                )
            except DockerNotFoundException:
                _logger.warning(
                    "browser_container_already_removed",
                    container_id=parameters.container_id,
                )
            model.active = False
            await self._browser_dao.save(model)
            _logger.info("browser_removed", container_id=parameters.container_id)
            return Browser.from_persistence(model)

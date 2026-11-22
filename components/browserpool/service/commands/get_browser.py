from typing import Final, override

import structlog
from browserpool.database import BrowserDAO, BrowserLoadEnum, ReadSession
from browserpool.domain_core import Command
from browserpool.service.dto import Browser
from browserpool.service.exceptions import BrowserNotFound
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class GetBrowserParameters(BaseModel):
    container_id: str


class GetBrowserCommand(Command[GetBrowserParameters, Browser]):
    """Read a single active browser by its container id."""

    def __init__(self, browser_dao: BrowserDAO[ReadSession]) -> None:
        self._browser_dao: BrowserDAO[ReadSession] = browser_dao

    @override
    async def __call__(self, parameters: GetBrowserParameters) -> Browser:
        with _tracer.start_as_current_span("service.get_browser") as span:
            span.set_attribute("request.container.id", parameters.container_id)
            model = await self._browser_dao.find_by_id(
                parameters.container_id, includes=[BrowserLoadEnum.SANDBOX]
            )
            if model is None or not model.active:
                raise BrowserNotFound(f"Browser {parameters.container_id} is not found")
            _logger.info("browser_fetched", container_id=parameters.container_id)
            return Browser.from_persistence(model)

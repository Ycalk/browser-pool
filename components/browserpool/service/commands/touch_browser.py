from datetime import UTC, datetime
from typing import Final, override

import structlog
from browserpool.database import BrowserDAO, BrowserLoadEnum, WriteSession
from browserpool.domain_core import Command
from browserpool.service.dto import Browser
from browserpool.service.exceptions import BrowserNotFound
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class TouchBrowserParameters(BaseModel):
    container_id: str


class TouchBrowserCommand(Command[TouchBrowserParameters, Browser]):
    """Extend the idle window of a browser by refreshing its last activity."""

    def __init__(self, browser_dao: BrowserDAO[WriteSession]) -> None:
        self._browser_dao: BrowserDAO[WriteSession] = browser_dao

    @override
    async def __call__(self, parameters: TouchBrowserParameters) -> Browser:
        with _tracer.start_as_current_span("service.touch_browser") as span:
            span.set_attribute("request.container.id", parameters.container_id)
            model = await self._browser_dao.find_by_id(
                parameters.container_id, includes=[BrowserLoadEnum.SANDBOX]
            )
            if model is None or not model.active:
                raise BrowserNotFound(f"Browser {parameters.container_id} is not found")
            model.last_touched_at = datetime.now(UTC)
            await self._browser_dao.save(model)
            _logger.info("browser_touched", container_id=parameters.container_id)
            return Browser.from_persistence(model)

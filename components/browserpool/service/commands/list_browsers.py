from typing import Final, override

import structlog
from browserpool.database import BrowserDAO, BrowserLoadEnum, ReadSession
from browserpool.domain_core import ParameterlessCommand
from browserpool.service.dto import Browser
from opentelemetry import trace

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ListBrowsersCommand(ParameterlessCommand[list[Browser]]):
    """List every active browser."""

    def __init__(self, browser_dao: BrowserDAO[ReadSession]) -> None:
        self._browser_dao: BrowserDAO[ReadSession] = browser_dao

    @override
    async def __call__(self) -> list[Browser]:
        with _tracer.start_as_current_span("service.list_browsers") as span:
            models = await self._browser_dao.find_active(
                includes=[BrowserLoadEnum.SANDBOX]
            )
            span.set_attribute("response.browsers.count", len(models))
            _logger.info("browsers_listed", count=len(models))
            return [Browser.from_persistence(model) for model in models]

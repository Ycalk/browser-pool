from typing import Final, override

import structlog
from browserpool.database import BrowserDAO, BrowserLoadEnum, ReadSession
from browserpool.domain_core import Command
from browserpool.service.dto import Browser
from browserpool.service.exceptions import BrowserNotFound
from opentelemetry import trace
from pydantic import BaseModel, Field

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ResolveBrowserParameters(BaseModel):
    container_id_prefix: str = Field(pattern=r"^[0-9a-f]{20}$")


class ResolveBrowserCommand(Command[ResolveBrowserParameters, Browser]):
    """Read a single active browser by the public 20 hex character id prefix."""

    def __init__(self, browser_dao: BrowserDAO[ReadSession]) -> None:
        self._browser_dao: BrowserDAO[ReadSession] = browser_dao

    @override
    async def __call__(self, parameters: ResolveBrowserParameters) -> Browser:
        with _tracer.start_as_current_span("service.resolve_browser") as span:
            span.set_attribute(
                "request.container.id_prefix", parameters.container_id_prefix
            )
            models = await self._browser_dao.find_by_id_prefix(
                parameters.container_id_prefix, includes=[BrowserLoadEnum.SANDBOX]
            )
            active = [model for model in models if model.active]
            if len(active) != 1:
                # An 80 bit prefix cannot collide in practice; refuse to guess
                # instead of routing a request to a foreign browser.
                if len(active) > 1:
                    _logger.error(
                        "browser_id_prefix_collision",
                        container_id_prefix=parameters.container_id_prefix,
                        container_ids=[model.container_id for model in active],
                    )
                raise BrowserNotFound(
                    "Browser with id prefix "
                    + f"{parameters.container_id_prefix} is not found"
                )
            _logger.info(
                "browser_resolved",
                container_id_prefix=parameters.container_id_prefix,
                container_id=active[0].container_id,
            )
            return Browser.from_persistence(active[0])

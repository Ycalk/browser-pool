from typing import Final, override

import structlog
from browserpool.container_driver import (
    RemoveContainerCommand,
    RemoveContainerParameters,
)
from browserpool.database import BrowserDAO, BrowserLoadEnum, WriteSession
from browserpool.domain_core import ParameterlessCommand
from browserpool.service.dto import Browser
from opentelemetry import trace

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ReapIdleBrowsersCommand(ParameterlessCommand[list[Browser]]):
    """Remove every active browser whose idle deadline has passed."""

    def __init__(
        self,
        browser_dao: BrowserDAO[WriteSession],
        remove_container: RemoveContainerCommand,
    ) -> None:
        self._browser_dao: BrowserDAO[WriteSession] = browser_dao
        self._remove_container: RemoveContainerCommand = remove_container

    @override
    async def __call__(self) -> list[Browser]:
        with _tracer.start_as_current_span("service.reap_idle_browsers") as span:
            expired = await self._browser_dao.find_expired(
                includes=[BrowserLoadEnum.SANDBOX]
            )
            span.set_attribute("response.browsers.expired", len(expired))

            reaped: list[Browser] = []
            for browser in expired:
                try:
                    await self._remove_container(
                        RemoveContainerParameters(id=browser.container_id, force=True)
                    )
                except Exception:
                    _logger.error(
                        "idle_browser_reap_failed",
                        container_id=browser.container_id,
                    )
                    continue
                browser.active = False
                await self._browser_dao.save(browser)
                reaped.append(Browser.from_persistence(browser))

            if reaped:
                span.set_attribute("response.browsers.reaped", len(reaped))
                _logger.info(
                    "idle_browsers_reaped",
                    count=len(reaped),
                    container_ids=[b.container_id for b in reaped],
                )
            return reaped

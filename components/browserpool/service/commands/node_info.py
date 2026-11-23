from importlib import metadata
from typing import Final, override

import structlog
from browserpool.database import BrowserDAO, ReadSession, SandboxDAO
from browserpool.domain_core import ParameterlessCommand
from browserpool.service.settings import ServiceSettings
from browserpool.variant import BrowserVariant, BrowserVariantInfo
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class NodeInfoResponse(BaseModel):
    version: str
    browser_limit: int
    sandboxes_active: int
    sandboxes_free: int
    browsers_active: int
    variants: list[BrowserVariantInfo]


class NodeInfoCommand(ParameterlessCommand[NodeInfoResponse]):
    """Report node capacity, usage and available browser variants."""

    def __init__(
        self,
        settings: ServiceSettings,
        sandbox_dao: SandboxDAO[ReadSession],
        browser_dao: BrowserDAO[ReadSession],
    ) -> None:
        self._settings: ServiceSettings = settings
        self._sandbox_dao: SandboxDAO[ReadSession] = sandbox_dao
        self._browser_dao: BrowserDAO[ReadSession] = browser_dao

    @override
    async def __call__(self) -> NodeInfoResponse:
        with _tracer.start_as_current_span("service.node_info") as span:
            sandboxes = await self._sandbox_dao.find_active()
            free_sandboxes = await self._sandbox_dao.find_active_without_browsers()
            browsers = await self._browser_dao.find_active()
            response = NodeInfoResponse(
                version=_package_version(),
                browser_limit=self._settings.browser_limit,
                sandboxes_active=len(sandboxes),
                sandboxes_free=len(free_sandboxes),
                browsers_active=len(browsers),
                variants=BrowserVariant.variants(),
            )
            span.set_attribute("response.sandboxes.active", response.sandboxes_active)
            span.set_attribute("response.sandboxes.free", response.sandboxes_free)
            span.set_attribute("response.browsers.active", response.browsers_active)
            _logger.info(
                "node_info_reported",
                sandboxes_active=response.sandboxes_active,
                sandboxes_free=response.sandboxes_free,
                browsers_active=response.browsers_active,
            )
            return response


def _package_version() -> str:
    for package in ("service", "browser-pool"):
        try:
            return metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"  # pragma: no cover - installed in production

from datetime import UTC, datetime
from typing import Final, override

import structlog
from browserpool.container_driver import (
    CreateContainerCommand,
    InspectContainerCommand,
    InspectContainerParameters,
    RemoveContainerCommand,
    RemoveContainerParameters,
    StartContainerCommand,
    StartContainerParameters,
)
from browserpool.database import (
    BrowserCreateParameters,
    BrowserDAO,
    BrowserLoadEnum,
    SandboxDAO,
    WriteSession,
)
from browserpool.domain_core import Command
from browserpool.service.dto import Browser
from browserpool.service.exceptions import (
    BrowserLimitExceeded,
    InvalidBrowserError,
    InvalidIdleTTL,
    InvalidSandboxError,
)
from browserpool.service.settings import ServiceSettings
from browserpool.variant import BrowserVariant
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class CreateBrowserParameters(BaseModel):
    variant: str
    idle_ttl_seconds: int


class CreateBrowserCommand(Command[CreateBrowserParameters, Browser]):
    """Create new browser instance."""

    def __init__(
        self,
        settings: ServiceSettings,
        create_container: CreateContainerCommand,
        start_container: StartContainerCommand,
        inspect_container: InspectContainerCommand,
        remove_container: RemoveContainerCommand,
        sandbox_dao: SandboxDAO[WriteSession],
        browser_dao: BrowserDAO[WriteSession],
    ) -> None:
        self._settings: ServiceSettings = settings
        self._create_container: CreateContainerCommand = create_container
        self._start_container: StartContainerCommand = start_container
        self._inspect_container: InspectContainerCommand = inspect_container
        self._remove_container: RemoveContainerCommand = remove_container
        self._sandbox_dao: SandboxDAO[WriteSession] = sandbox_dao
        self._browser_dao: BrowserDAO[WriteSession] = browser_dao

    @override
    async def __call__(self, parameters: CreateBrowserParameters) -> Browser:
        with _tracer.start_as_current_span("service.create_browser") as span:
            span.set_attribute("request.browser.variant", parameters.variant)
            span.set_attribute(
                "request.browser.idle_ttl_seconds", parameters.idle_ttl_seconds
            )
            if (
                parameters.idle_ttl_seconds
                < self._settings.browser_min_idle_ttl_seconds
            ):
                raise InvalidIdleTTL(
                    "Browser IDLE TTL cannot be "
                    + f"less than: {self._settings.browser_min_idle_ttl_seconds}"
                )
            if (
                parameters.idle_ttl_seconds
                > self._settings.browser_max_idle_ttl_seconds
            ):
                raise InvalidIdleTTL(
                    "Browser IDLE TTL cannot be "
                    + f"more than: {self._settings.browser_max_idle_ttl_seconds}"
                )

            sandboxes = await self._sandbox_dao.find_active_without_browsers()
            if len(sandboxes) == 0:
                raise BrowserLimitExceeded("Cannot create more browsers")
            sandbox = sandboxes[0]

            span.set_attribute("browser.network.name", sandbox.network_name)
            created_at = datetime.now(UTC)
            labels = {
                self._settings.managed_label: "true",
                self._settings.browser_variant_label: parameters.variant,
                self._settings.browser_sandbox_network_id_label: sandbox.network_id,
                self._settings.browser_idle_ttl_seconds_label: str(
                    parameters.idle_ttl_seconds
                ),
                self._settings.browser_created_at_label: str(
                    int(created_at.timestamp())
                ),
            }
            variant = BrowserVariant.get_variant(
                parameters.variant,
                container_name=f"{self._settings.browser_container_prefix}-{sandbox.index}",
                network_name=sandbox.network_name,
                labels=labels,
            )

            container_id: str | None = None
            try:
                container = await self._create_container(variant.container_config)
                container_id = container.container_id
                _logger.info("container_created")
                span.set_attribute("browser.container.id", container_id)

                await self._start_container(
                    StartContainerParameters(container_id=container.container_id)
                )
                detail = await self._inspect_container(
                    InspectContainerParameters(id=container.container_id)
                )
                network = detail.networks.get(sandbox.network_name)
                if network is None or network.ip_address == "":
                    raise InvalidBrowserError(
                        f"Container {container.container_id} is not attached to "
                        + f"{sandbox.network_name}"
                    )
                if network.network_id != sandbox.network_id:
                    raise InvalidSandboxError(
                        f"Unexpected network id. Expect {sandbox.network_id[:12]}. "
                        + f"Got: {network.network_id[:12]}"
                    )

                await variant.wait_until_ready(
                    network.ip_address,
                    self._settings.variant_readiness_timeout_seconds,
                )
                _logger.info("container_started")
                await self._browser_dao.create(
                    BrowserCreateParameters(
                        container_id=container.container_id,
                        network_id=sandbox.network_id,
                        variant=variant.name,
                        host=network.ip_address,
                        port=variant.development_protocol_port,
                        idle_ttl_seconds=parameters.idle_ttl_seconds,
                        created_at=created_at,
                    )
                )
            except Exception:
                if container_id is not None:
                    await self._remove_container(
                        RemoveContainerParameters(id=container_id, force=True)
                    )
                raise

            _logger.info(
                "browser_created",
                container_id=container.container_id,
            )

            browser = await self._browser_dao.find_by_id(
                container.container_id, includes=[BrowserLoadEnum.SANDBOX]
            )
            if browser is None:
                raise RuntimeError("Browser not found after creation")

            return Browser.from_persistence(browser)

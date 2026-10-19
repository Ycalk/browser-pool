from datetime import UTC, datetime
from typing import Final, override

import structlog
from browserpool.container_driver import (
    ContainerSummaryResponse,
    InspectContainerCommand,
    InspectContainerParameters,
    LabelFilters,
    ListContainersCommand,
    ListContainersParameters,
    RemoveContainerCommand,
    RemoveContainerParameters,
)
from browserpool.database import (
    BrowserCreateParameters,
    BrowserDAO,
    BrowserLoadEnum,
    ReadSession,
    SandboxDAO,
    WriteSession,
)
from browserpool.domain_core import ParameterlessCommand
from browserpool.service.dto import Browser
from browserpool.service.settings import ServiceSettings
from browserpool.variant import BrowserVariant
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ReconcileBrowsersResponse(BaseModel):
    adopted: list[Browser] = []
    deactivated: list[Browser] = []
    reactivated: list[Browser] = []
    removed: list[str] = []
    stranded: list[Browser] = []


class ReconcileBrowsersCommand(ParameterlessCommand[ReconcileBrowsersResponse]):
    """Synchronize browser containers between Docker and the database."""

    def __init__(
        self,
        settings: ServiceSettings,
        browser_dao: BrowserDAO[WriteSession],
        sandbox_dao: SandboxDAO[ReadSession],
        list_containers: ListContainersCommand,
        inspect_container: InspectContainerCommand,
        remove_container: RemoveContainerCommand,
    ) -> None:
        self._settings: ServiceSettings = settings
        self._browser_dao: BrowserDAO[WriteSession] = browser_dao
        self._sandbox_dao: SandboxDAO[ReadSession] = sandbox_dao
        self._list_containers: ListContainersCommand = list_containers
        self._inspect_container: InspectContainerCommand = inspect_container
        self._remove_container: RemoveContainerCommand = remove_container

    @override
    async def __call__(self) -> ReconcileBrowsersResponse:
        with _tracer.start_as_current_span("service.reconcile_browsers") as span:
            containers = await self._list_containers(
                ListContainersParameters(
                    all=True,
                    filters=LabelFilters(labels={self._settings.managed_label: "true"}),
                )
            )
            docker_containers: dict[str, ContainerSummaryResponse] = {
                c.id: c for c in containers
            }

            browsers = await self._browser_dao.find_all(
                includes=[BrowserLoadEnum.SANDBOX]
            )
            browser_by_container_id = {b.container_id: b for b in browsers}

            adopted: list[Browser] = []
            deactivated: list[Browser] = []
            reactivated: list[Browser] = []
            removed: list[str] = []

            # 1. Reconcile existing rows against the live containers.
            for browser in browsers:
                container = docker_containers.get(browser.container_id)
                if container is None:
                    if browser.active:
                        browser.active = False
                        await self._browser_dao.save(browser)
                        deactivated.append(Browser.from_persistence(browser))
                    continue
                if not browser.active:
                    browser.active = True
                    await self._browser_dao.save(browser)
                    reactivated.append(Browser.from_persistence(browser))

            # 2. Adopt untracked managed containers whose sandbox is active, or
            #    remove orphans past the grace window.
            for container in docker_containers.values():
                if container.id in browser_by_container_id:
                    continue
                adoption = await self._adopt(container)
                if adoption is not None:
                    adopted.append(adoption)
                else:
                    await self._remove_container(
                        RemoveContainerParameters(id=container.id, force=True)
                    )
                    removed.append(container.id)
                    _logger.info(
                        "orphan_container_removed",
                        container_id=container.id,
                        name=container.name,
                    )

            # 3. Stranded browsers: active rows whose sandbox got deactivated.
            stranded_models = await self._browser_dao.find_active_in_inactive_sandboxes(
                includes=[BrowserLoadEnum.SANDBOX]
            )
            stranded: list[Browser] = []
            for browser in stranded_models:
                try:
                    await self._remove_container(
                        RemoveContainerParameters(id=browser.container_id, force=True)
                    )
                except Exception:
                    _logger.exception(
                        "stranded_browser_remove_failed",
                        container_id=browser.container_id,
                    )
                    continue
                browser.active = False
                await self._browser_dao.save(browser)
                stranded.append(Browser.from_persistence(browser))
                _logger.info(
                    "stranded_browser_removed",
                    container_id=browser.container_id,
                    network_id=browser.network_id,
                )

            span.set_attribute("response.browsers.adopted", len(adopted))
            span.set_attribute("response.browsers.deactivated", len(deactivated))
            span.set_attribute("response.browsers.reactivated", len(reactivated))
            span.set_attribute("response.browsers.removed", len(removed))
            span.set_attribute("response.browsers.stranded", len(stranded))
            _logger.info(
                "browsers_reconciled",
                adopted=len(adopted),
                deactivated=len(deactivated),
                reactivated=len(reactivated),
                removed=len(removed),
                stranded=len(stranded),
            )
            return ReconcileBrowsersResponse(
                adopted=adopted,
                deactivated=deactivated,
                reactivated=reactivated,
                removed=removed,
                stranded=stranded,
            )

    async def _adopt(self, container: ContainerSummaryResponse) -> Browser | None:
        labels = container.labels or {}
        variant = labels.get(self._settings.browser_variant_label)
        network_id = labels.get(self._settings.browser_sandbox_network_id_label)
        ttl_raw = labels.get(self._settings.browser_idle_ttl_seconds_label)
        created_raw = labels.get(self._settings.browser_created_at_label)

        if (
            (variant is None)
            or (network_id is None)
            or (ttl_raw is None)
            or (created_raw is None)
        ):
            return None

        sandbox = await self._sandbox_dao.find_by_id(network_id)
        if sandbox is None or not sandbox.active:
            return None

        try:
            idle_ttl_seconds = int(ttl_raw)
        except ValueError:
            return None

        try:
            created_at = datetime.fromtimestamp(int(created_raw), tz=UTC)
        except ValueError:
            return None

        detail = await self._inspect_container(
            InspectContainerParameters(id=container.id)
        )
        network = detail.networks.get(sandbox.network_name)
        if network is None or network.ip_address == "":
            return None

        try:
            browser_variant = BrowserVariant.get_variant(
                variant,
                container_name=detail.name,
                network_name=sandbox.network_name,
                labels={},
            )
        except Exception:
            _logger.warning("adopt_port_unknown_variant", variant=variant)
            return None

        model = await self._browser_dao.create(
            BrowserCreateParameters(
                container_id=container.id,
                network_id=sandbox.network_id,
                variant=variant,
                host=network.ip_address,
                port=browser_variant.development_protocol_port,
                idle_ttl_seconds=idle_ttl_seconds,
                last_touched_at=created_at,
                created_at=created_at,
            )
        )
        _logger.info(
            "browser_adopted",
            container_id=container.id,
            variant=variant,
            network_id=sandbox.network_id,
        )
        return Browser.from_persistence(model)

from typing import Final, Literal, override

import structlog
from browserpool.container_driver import (
    ConnectNetworkCommand,
    ConnectNetworkParameters,
    CreateNetworkCommand,
    InspectContainerCommand,
    InspectContainerParameters,
    LabelFilters,
    ListNetworksCommand,
    NetworkConfig,
    NetworkResponse,
)
from browserpool.database import Sandbox as SandboxPersistence
from browserpool.database import SandboxCreateParameters, SandboxDAO, WriteSession
from browserpool.domain_core import ParameterlessCommand
from browserpool.service.dto import Sandbox
from browserpool.service.exceptions import InvalidSandboxError
from browserpool.service.settings import ServiceSettings
from opentelemetry import trace
from pydantic import BaseModel

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class ReconcileSandboxesResponse(BaseModel):
    created: list[Sandbox] = []
    adopted: list[Sandbox] = []
    deactivated: list[Sandbox] = []
    reactivated: list[Sandbox] = []
    attached: list[str] = []


class ReconcileSandboxesCommand(ParameterlessCommand[ReconcileSandboxesResponse]):
    """Synchronize sandbox networks between Docker and the database."""

    def __init__(
        self,
        settings: ServiceSettings,
        sandbox_dao: SandboxDAO[WriteSession],
        list_networks: ListNetworksCommand,
        create_network: CreateNetworkCommand,
        inspect_container: InspectContainerCommand,
        connect_network: ConnectNetworkCommand,
    ) -> None:
        self._settings: ServiceSettings = settings
        self._sandbox_dao: SandboxDAO[WriteSession] = sandbox_dao
        self._list_networks: ListNetworksCommand = list_networks
        self._create_network: CreateNetworkCommand = create_network
        self._inspect_container: InspectContainerCommand = inspect_container
        self._connect_network: ConnectNetworkCommand = connect_network

    @override
    async def __call__(self) -> ReconcileSandboxesResponse:
        with _tracer.start_as_current_span("service.reconcile_sandboxes") as span:
            span.set_attribute("request.sandbox.limit", self._settings.browser_limit)

            networks = await self._list_networks(
                LabelFilters(labels={self._settings.managed_label: "true"})
            )
            docker_networks: dict[str, NetworkResponse] = {
                net.id: net for net in networks
            }

            sandboxes = await self._sandbox_dao.find_all()
            sandboxes_by_network_id = {sb.network_id: sb for sb in sandboxes}

            created: list[Sandbox] = []
            adopted: list[Sandbox] = []
            deactivated: list[Sandbox] = []
            reactivated: list[Sandbox] = []

            # 1. Adopt/reactivate/deactivate based on the current Docker state.
            for network in docker_networks.values():
                try:
                    network_process_result = await self._process_network(
                        network, sandboxes_by_network_id
                    )
                except Exception:
                    continue
                if network_process_result is not None:
                    action, sandbox = network_process_result
                    if action == "adopted":
                        adopted.append(sandbox)
                    if action == "reactivated":
                        reactivated.append(sandbox)

            for sandbox in sandboxes:
                if sandbox.active and sandbox.network_id not in docker_networks:
                    sandbox.active = False
                    await self._sandbox_dao.save(sandbox)
                    deactivated.append(Sandbox.from_persistence(sandbox))

            # 2. Fill up to browser_limit.
            active = await self._sandbox_dao.find_active()
            used_indices = {sb.index for sb in active}
            for index in range(self._settings.browser_limit):
                if index in used_indices:
                    continue
                sandbox = await self._create_sandbox(index)
                if sandbox is None:
                    continue
                created.append(sandbox)

            # 3. Attach the service container to every active sandbox it lacks.
            attached = await self._attach_service_container()

            span.set_attribute("response.sandboxes.created", len(created))
            span.set_attribute("response.sandboxes.adopted", len(adopted))
            span.set_attribute("response.sandboxes.deactivated", len(deactivated))
            span.set_attribute("response.sandboxes.reactivated", len(reactivated))
            span.set_attribute("response.sandboxes.attached", len(attached))
            _logger.info(
                "sandboxes_reconciled",
                created=len(created),
                adopted=len(adopted),
                deactivated=len(deactivated),
                reactivated=len(reactivated),
                attached=len(attached),
            )
            return ReconcileSandboxesResponse(
                created=created,
                adopted=adopted,
                deactivated=deactivated,
                reactivated=reactivated,
                attached=attached,
            )

    async def _process_network(
        self,
        network: NetworkResponse,
        sandboxes_by_network_id: dict[str, SandboxPersistence],
    ) -> tuple[Literal["adopted", "reactivated"], Sandbox] | None:
        with _tracer.start_as_current_span(
            "service.reconcile_sandboxes.process_network"
        ) as span:
            span.set_attribute("network.id", network.id)
            span.set_attribute("network.name", network.name)
            sandbox = sandboxes_by_network_id.get(network.id)
            if sandbox is None:
                index_label = (
                    network.labels.get(self._settings.sandbox_index_label)
                    if network.labels is not None
                    else None
                )
                if index_label is None:
                    _logger.error(
                        "managed_network_unadoptable",
                        network_id=network.id,
                        network_name=network.name,
                    )
                    raise InvalidSandboxError(
                        f"Network {network.name} does not have "
                        + f"{self._settings.sandbox_index_label} label"
                    )
                try:
                    index = int(index_label)
                except ValueError:
                    _logger.error(
                        "managed_network_unadoptable",
                        network_id=network.id,
                        network_name=network.name,
                    )
                    raise InvalidSandboxError(
                        "Cannot cast to int label "
                        + f"{self._settings.sandbox_index_label} "
                        + f"in network {network.name}"
                    )
                # Refuse to adopt if an active slot already holds this index.
                existing = await self._sandbox_dao.find_active_by_index(index)
                if existing is not None:
                    _logger.error(
                        "sandbox_index_collision",
                        index=index,
                        existing_network_id=existing.network_id,
                        new_network_id=network.id,
                    )
                    raise InvalidSandboxError(
                        f"Network {network.name} does have "
                        + f"same index as {existing.network_name}"
                    )
                _logger.info(
                    "creating_record_for_existing_network",
                    network_id=network.id,
                    network_name=network.name,
                )
                model = await self._sandbox_dao.create(
                    SandboxCreateParameters(
                        network_id=network.id,
                        network_name=network.name,
                        index=index,
                    )
                )
                span.set_attribute("action", "adopted")
                return ("adopted", Sandbox.from_persistence(model))
            if not sandbox.active:
                # Network reappeared; reactivate if the index is still free.
                holder = await self._sandbox_dao.find_active_by_index(sandbox.index)
                if holder is not None and holder.network_id != sandbox.network_id:
                    _logger.error(
                        "sandbox_reactivate_index_taken",
                        network_id=sandbox.network_id,
                        index=sandbox.index,
                        holder_network_id=holder.network_id,
                    )
                    raise InvalidSandboxError(
                        f"Cannot reactivate sandbox with network {network.name}. "
                        + f"There is a network {holder.network_name} "
                        + "with the same index"
                    )
                sandbox.active = True
                await self._sandbox_dao.save(sandbox)
                span.set_attribute("action", "reactivated")
                return ("reactivated", Sandbox.from_persistence(sandbox))

    async def _create_sandbox(self, index: int):
        name = f"{self._settings.browser_slot_network_prefix}-{index}"
        try:
            response = await self._create_network(
                NetworkConfig(
                    name=name,
                    driver="bridge",
                    labels={
                        self._settings.managed_label: "true",
                        self._settings.sandbox_index_label: str(index),
                    },
                )
            )
        except Exception:
            _logger.error(
                "sandbox_network_create_failed", index=index, network_name=name
            )
            return
        _logger.info(
            "sandbox_network_created",
            index=index,
            network_id=response.network_id,
            network_name=name,
        )
        sandbox = await self._sandbox_dao.create(
            SandboxCreateParameters(
                network_id=response.network_id,
                network_name=name,
                index=index,
            )
        )
        return Sandbox.from_persistence(sandbox)

    async def _attach_service_container(self) -> list[str]:
        attached: list[str] = []
        container_id = self._settings.browser_service_container_id
        if container_id is None:
            _logger.warning("service_container_not_configured")
            return attached

        detail = await self._inspect_container(
            InspectContainerParameters(id=container_id)
        )

        attached_names = set(detail.networks)
        active = await self._sandbox_dao.find_active()
        for sandbox in active:
            if sandbox.network_name in attached_names:
                continue
            await self._connect_network(
                ConnectNetworkParameters(
                    network_id=sandbox.network_id, container_id=container_id
                )
            )
            attached.append(sandbox.network_name)
            _logger.info(
                "service_attached_to_sandbox",
                index=sandbox.index,
                network=sandbox.network_name,
            )
        return attached

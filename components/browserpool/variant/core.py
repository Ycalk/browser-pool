import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Final, Self, TypedDict

import structlog
from browserpool.container_driver import ContainerConfig
from browserpool.variant.exceptions import (
    BrowserConfigurationError,
    BrowserNotReadyError,
)
from opentelemetry import trace

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)


class BrowserVariantInfo(TypedDict):
    name: str
    image_name: str
    image_tag: str


class BrowserVariant(ABC):
    _variants: ClassVar[dict[str, type[Self]]] = {}

    def __init__(
        self,
        variant_name: str,
        container_name: str,
        network_name: str,
        labels: dict[str, str],
    ) -> None:
        self._variant_name: str = variant_name
        self._container_name: str = container_name
        self._network_name: str = network_name
        self._labels: dict[str, str] = labels

    @property
    @abstractmethod
    def container_config(self) -> ContainerConfig: ...

    @property
    @abstractmethod
    def development_protocol_port(self) -> int: ...

    @classmethod
    @abstractmethod
    def image_name(cls) -> str: ...

    @classmethod
    @abstractmethod
    def image_tag(cls) -> str: ...

    @abstractmethod
    async def _is_ready(self, prob_host: str) -> bool: ...

    def __init_subclass__(cls, name: str, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            BrowserVariant._variants[name] = cls

    @classmethod
    def get_variant(
        cls,
        name: str,
        *,
        container_name: str,
        network_name: str,
        labels: dict[str, str],
        **variant_kwargs: Any,
    ) -> Self:
        variant = cls._variants.get(name)
        if variant is None:
            raise BrowserConfigurationError(
                f"No image configured for browser variant {name}"
            )
        return variant(
            variant_name=name,
            container_name=container_name,
            network_name=network_name,
            labels=labels,
            **variant_kwargs,
        )

    @property
    def name(self) -> str:
        return self._variant_name

    @classmethod
    def variants(cls) -> list[BrowserVariantInfo]:
        return [
            BrowserVariantInfo(
                name=name, image_name=var.image_name(), image_tag=var.image_tag()
            )
            for name, var in cls._variants.items()
        ]

    async def wait_until_ready(
        self,
        probe_host: str,
        timeout_seconds: float,
    ) -> None:
        with _tracer.start_as_current_span("browser.wait_until_ready") as span:
            span.set_attribute("request.browser.type", self._variant_name)
            span.set_attribute("request.browser.host", probe_host)
            span.set_attribute(
                "request.browser.development_protocol_port",
                self.development_protocol_port,
            )
            _logger.info(
                "waiting_for_readiness",
                browser_type=self._variant_name,
                host=probe_host,
                port=self.development_protocol_port,
                timeout_seconds=timeout_seconds,
            )

            start_time = time.time()
            while True:
                if await self._is_ready(probe_host):
                    _logger.info(
                        "browser_ready",
                        browser_type=self._variant_name,
                        host=probe_host,
                        port=self.development_protocol_port,
                    )
                    return
                if time.time() - start_time > timeout_seconds:
                    raise BrowserNotReadyError(
                        f"{self._variant_name.capitalize()} browser "
                        + f"did not become ready within {timeout_seconds} seconds"
                    )
                await asyncio.sleep(1)

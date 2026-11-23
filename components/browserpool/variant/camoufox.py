import asyncio
from contextlib import suppress
from typing import ClassVar, Final, override

from browserpool.container_driver import (
    ContainerConfig,
    EndpointConfig,
    HostConfig,
    NetworkingConfig,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from .core import BrowserVariant


class _CamoufoxBrowserSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    camoufox_image_name: str
    camoufox_image_tag: str
    camoufox_playwright_port: int = 9222


_settings: Final[_CamoufoxBrowserSettings] = _CamoufoxBrowserSettings()  # pyright: ignore[reportCallIssue]


class CamoufoxBrowser(BrowserVariant, name="camoufox"):
    @property
    @override
    def container_config(self) -> ContainerConfig:
        return ContainerConfig(
            image=f"{_settings.camoufox_image_name}:{_settings.camoufox_image_tag}",
            name=self._container_name,
            detach=True,
            labels=self._labels,
            networking_config=NetworkingConfig(
                endpoints_config={self._network_name: EndpointConfig()}
            ),
            # The display keeper restarts the container when Firefox loses its
            # only window: after an external close every new page fails with
            # "window is null", so an in-process restart cannot recover.
            host_config=HostConfig(restart_policy="unless-stopped"),
        )

    @property
    @override
    def development_protocol_port(self) -> int:
        return _settings.camoufox_playwright_port

    @classmethod
    @override
    def image_name(cls) -> str:
        return _settings.camoufox_image_name

    @classmethod
    @override
    def image_tag(cls) -> str:
        return _settings.camoufox_image_tag

    @override
    async def _is_ready(self, prob_host: str) -> bool:
        try:
            async with asyncio.timeout(1):
                _, writer = await asyncio.open_connection(
                    prob_host, _settings.camoufox_playwright_port
                )
        except (OSError, TimeoutError):
            return False
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
        return True

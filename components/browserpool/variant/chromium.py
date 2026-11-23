from typing import ClassVar, Final, override

import httpx
from browserpool.container_driver import (
    ContainerConfig,
    EndpointConfig,
    HostConfig,
    NetworkingConfig,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from .core import BrowserVariant


class _ChromiumBrowserSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    chromium_image_name: str
    chromium_image_tag: str
    chromium_development_protocol_port: int = 9222


_settings: Final[_ChromiumBrowserSettings] = _ChromiumBrowserSettings()  # pyright: ignore[reportCallIssue]


class ChromiumBrowser(BrowserVariant, name="chromium"):
    @property
    @override
    def container_config(self) -> ContainerConfig:
        return ContainerConfig(
            image=f"{_settings.chromium_image_name}:{_settings.chromium_image_tag}",
            name=self._container_name,
            detach=True,
            labels=self._labels,
            networking_config=NetworkingConfig(
                endpoints_config={self._network_name: EndpointConfig()}
            ),
            host_config=HostConfig(restart_policy="unless-stopped"),
        )

    @property
    @override
    def development_protocol_port(self) -> int:
        return _settings.chromium_development_protocol_port

    @classmethod
    @override
    def image_name(cls) -> str:
        return _settings.chromium_image_name

    @classmethod
    @override
    def image_tag(cls) -> str:
        return _settings.chromium_image_tag

    @override
    async def _is_ready(self, prob_host: str) -> bool:
        async with httpx.AsyncClient(timeout=2) as client:
            try:
                response = await client.get(
                    f"http://{prob_host}:{_settings.chromium_development_protocol_port}/json/version"
                )
            except httpx.HTTPError:
                return False
        return response.status_code == 200

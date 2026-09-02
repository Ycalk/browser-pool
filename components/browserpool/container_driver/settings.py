from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class ContainerDriverSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    docker_host: str = "/var/run/docker.sock"
    docker_api_version: str = "v1.55"
    docker_timeout_seconds: int = 30

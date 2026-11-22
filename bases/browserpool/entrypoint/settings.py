from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class EntrypointSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Browserpool API"
    api_prefix: str = "/api"
    api_port: int = 8080
    api_secret_key: str

    @property
    def methods_prefix(self) -> str:
        return f"{self.api_prefix}/v1"

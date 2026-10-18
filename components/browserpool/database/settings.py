from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    sqlite_database_path: str = "browserpool.db"

    sqlite_pool_size: int = 5
    sqlite_max_overflow: int = 10
    sqlite_pool_timeout: float = 30

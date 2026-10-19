from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    browser_limit: int
    browser_slot_network_prefix: str = "browserpool-sandbox"
    browser_container_prefix: str = "browserpool-browser"
    browser_min_idle_ttl_seconds: int = 60
    browser_max_idle_ttl_seconds: int = 60 * 60 * 24
    variant_readiness_timeout_seconds: int = 90
    browser_service_container_id: str | None = None

    managed_label: str = "browserpool.managed"
    browser_variant_label: str = "browserpool.browser.variant"
    browser_sandbox_network_id_label: str = "browserpool.browser.sandbox.network_id"
    browser_idle_ttl_seconds_label: str = "browserpool.browser.idle_ttl_seconds"
    browser_created_at_label: str = "browserpool.browser.created_at"
    sandbox_index_label: str = "browserpool.sandbox.index"

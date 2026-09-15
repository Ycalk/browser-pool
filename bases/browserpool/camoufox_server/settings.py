from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CamoufoxServerSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    playwright_port: int = 9222
    playwright_host: str = "0.0.0.0"
    playwright_path: Annotated[
        str, AfterValidator(lambda p: p if p.startswith("/") else f"/{p}")
    ] = "/playwright"

    camoufox_os: Literal["macos", "windows", "linux"] = "linux"
    screen_width: int = 1920
    screen_height: int = 1080
    panel_height: int = 27
    camoufox_proxy: str | None = None

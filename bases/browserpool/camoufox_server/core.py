from urllib.parse import urlsplit

from camoufox.server import launch_server
from dishka import Provider, Scope, make_container, provide

from .settings import CamoufoxServerSettings


class CamoufoxServerProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> CamoufoxServerSettings:
        return CamoufoxServerSettings()


def _display_config(settings: CamoufoxServerSettings) -> dict[str, int]:
    work_height = max(1, settings.screen_height - settings.panel_height)
    return {
        "screen.width": settings.screen_width,
        "screen.height": settings.screen_height,
        "screen.availWidth": settings.screen_width,
        "screen.availHeight": work_height,
        "window.outerWidth": settings.screen_width,
        "window.outerHeight": work_height,
        "window.screenX": 0,
        "window.screenY": 0,
    }


def _get_proxy(settings: CamoufoxServerSettings) -> dict[str, str] | None:
    if settings.camoufox_proxy is None:
        return None

    raw_proxy = settings.camoufox_proxy.strip()
    if "://" not in raw_proxy:
        raw_proxy = f"//{raw_proxy}"
    parsed = urlsplit(raw_proxy)
    protocol = parsed.scheme if parsed.scheme != "" else "http"
    if parsed.hostname is None:
        raise ValueError(f"Failed to extract hostname from string: {raw_proxy}")
    if parsed.port is None:
        raise ValueError(f"Failed to extract port from string: {raw_proxy}")

    result = {
        "server": f"{protocol}://{parsed.hostname}:{parsed.port}",
    }
    if parsed.username is not None:
        result["username"] = parsed.username
    if parsed.password is not None:
        result["password"] = parsed.password
    return result


def run():
    container = make_container(CamoufoxServerProvider())
    settings = container.get(CamoufoxServerSettings)

    config = _display_config(settings)
    launch_server(
        host=settings.playwright_host,
        port=settings.playwright_port,
        ws_path=settings.playwright_path,
        config=config,
        os=settings.camoufox_os,
        proxy=_get_proxy(settings),
        humanize=True,
        geoip=True,
        i_know_what_im_doing=True,
    )

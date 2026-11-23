import asyncio
import contextlib
import logging
import os
import threading
from typing import Final
from urllib.parse import urlsplit

from camoufox.server import launch_server
from dishka import Provider, Scope, make_container, provide
from playwright.async_api import Browser, async_playwright

from .settings import CamoufoxServerSettings

_logger: Final[logging.Logger] = logging.getLogger(__name__)
if not _logger.handlers:
    _handler: logging.Handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] display keeper: %(message)s")
    )
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)
_logger.propagate = False

_DISPLAY_RETRY_SECONDS: Final[float] = 5.0
_PAGE_WATCH_SECONDS: Final[float] = 1.0
_PAGE_TIMEOUT_SECONDS: Final[float] = 10.0
_PAGE_ATTEMPTS: Final[int] = 30


class CamoufoxServerProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> CamoufoxServerSettings:
        return CamoufoxServerSettings()


async def _hold_page(browser: Browser) -> None:
    """Create the keeper page on an established connection and keep it alive.

    The connection is never dropped while the browser has no window: a client
    that disconnects mid-startup can leave Playwright's Firefox without a window
    and every later ``new_page`` fails with ``window is null``. The page is also
    recreated when it is closed on the X display (Ctrl+W in KasmVNC, a crash),
    otherwise the preview stays black until a client happens to open a page.
    """
    for attempt in range(_PAGE_ATTEMPTS):
        context = None
        try:
            context = await asyncio.wait_for(
                browser.new_context(), _PAGE_TIMEOUT_SECONDS
            )
            page = await asyncio.wait_for(context.new_page(), _PAGE_TIMEOUT_SECONDS)
        except Exception:
            _logger.warning("page attempt %s failed", attempt + 1, exc_info=True)
            if context is not None:
                with contextlib.suppress(Exception):
                    await context.close()
            await asyncio.sleep(1.0)
            continue

        _logger.info("page is up, display stays alive")
        while browser.is_connected() and not page.is_closed():
            await asyncio.sleep(_PAGE_WATCH_SECONDS)

        if not browser.is_connected():
            _logger.warning("connection dropped, reconnecting")
            return

        _logger.warning("page was closed, recreating")
        with contextlib.suppress(Exception):
            await context.close()

    _logger.critical(
        "browser cannot create a window anymore, restarting the container"
    )
    os._exit(1)


async def _keep_display_alive(endpoint: str) -> None:
    """Hold one browser context so the X display is never empty.

    Playwright's server creates no browser context on its own and Firefox maps a
    window only for a context, so KasmVNC shows a black screen until the first
    client connects. A spare blank page fixes the preview and stays isolated
    from the contexts clients create.
    """
    while True:
        try:
            async with async_playwright() as playwright:
                browser = await playwright.firefox.connect(endpoint, timeout=30_000)
                _logger.info("connected to %s", endpoint)
                await _hold_page(browser)
        except Exception:
            _logger.warning("lost %s", endpoint, exc_info=True)
        await asyncio.sleep(_DISPLAY_RETRY_SECONDS)


def _start_display_keeper(endpoint: str) -> None:
    def runner() -> None:
        try:
            asyncio.run(_keep_display_alive(endpoint))
        except Exception:
            _logger.exception("crashed")

    threading.Thread(target=runner, name="display-keeper", daemon=True).start()


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

    endpoint = f"ws://127.0.0.1:{settings.playwright_port}{settings.playwright_path}"
    _start_display_keeper(endpoint)

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

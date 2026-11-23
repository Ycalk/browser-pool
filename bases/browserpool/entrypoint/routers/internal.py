from typing import Annotated, Final

import structlog
from browserpool.entrypoint.security import localhost_only
from browserpool.service import (
    Browser,
    BrowserNotFound,
    ResolveBrowserCommand,
    ResolveBrowserParameters,
    TouchBrowserCommand,
    TouchBrowserParameters,
)
from browserpool.variant import BrowserVariant
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Path, Response, Security, status
from fastapi.responses import JSONResponse

_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    route_class=DishkaRoute,
)


def _resolution_headers(browser: Browser) -> dict[str, str]:
    vnc_port = BrowserVariant.vnc_port_for(browser.variant)
    return {
        "X-Browser-Id": browser.container_id,
        "X-Browser-Vnc-Upstream": f"{browser.host}:{vnc_port}",
        "X-Browser-Dev-Upstream": f"{browser.host}:{browser.port}",
    }


@router.get("/browsers/{container_id_prefix}", include_in_schema=False)
async def resolve_browser(
    container_id_prefix: Annotated[str, Path(pattern=r"^[0-9a-f]{20}$")],
    resolve: FromDishka[ResolveBrowserCommand],
    touch: FromDishka[TouchBrowserCommand],
    _localhost: None = Security(localhost_only),
) -> Response:
    """Resolve the public 20 hex character id prefix for nginx subrequests.

    The caller is nginx itself (``auth_request``), so the answer has to stay a
    2xx for a hit: nginx only forwards 401/403 from an auth subrequest and turns
    every other error into a 500. A miss is reported as 403, which nginx maps to
    the public 404.
    """
    try:
        browser = await resolve(
            ResolveBrowserParameters(container_id_prefix=container_id_prefix)
        )
        await touch(TouchBrowserParameters(container_id=browser.container_id))
    except BrowserNotFound:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    return JSONResponse(
        content=browser.model_dump(),
        headers=_resolution_headers(browser),
    )

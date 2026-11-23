import asyncio
import contextlib
import time
from typing import Final, cast

import httpx
import structlog
import websockets
from browserpool.entrypoint.exceptions import CustomHTTPException
from browserpool.service import (
    GetBrowserCommand,
    GetBrowserParameters,
    TouchBrowserCommand,
    TouchBrowserParameters,
)
from dishka import AsyncContainer, Scope
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request, Response, WebSocket
from starlette.websockets import WebSocketState
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State
from websockets.typing import Origin, Subprotocol

_logger: Final[structlog.BoundLogger] = structlog.get_logger(__name__)

_HOP_BY_HOP_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "accept-encoding",
        "authorization",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

_TOUCH_INTERVAL_SECONDS: Final[float] = 5.0

router = APIRouter(
    prefix="/browsers/{container_id}/proxy",
    tags=["proxy"],
    route_class=DishkaRoute,
)


async def proxy_http(
    request: Request,
    container_id: str,
    path: str,
    get_browser: FromDishka[GetBrowserCommand],
    touch: FromDishka[TouchBrowserCommand],
    client: FromDishka[httpx.AsyncClient],
) -> Response:
    browser = await get_browser(GetBrowserParameters(container_id=container_id))
    await touch(TouchBrowserParameters(container_id=container_id))

    upstream_url = f"http://{browser.host}:{browser.port}/{path}"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }

    try:
        upstream = await client.request(
            request.method,
            upstream_url,
            headers=headers,
            params=cast(
                list[tuple[str, str | int | float | bool | None]],
                request.query_params.multi_items(),
            ),
            content=await request.body(),
        )
    except httpx.HTTPError as exc:
        _logger.warning(
            "proxy_http_failed",
            container_id=container_id,
            error=str(exc),
        )
        raise CustomHTTPException(
            error="ProxyError",
            status_code=502,
            message=f"Upstream request failed: {exc}",
        ) from exc

    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
    )
    for key, value in upstream.headers.multi_items():
        if key.lower() not in _HOP_BY_HOP_HEADERS:
            response.headers.append(key, value)
    return response


for _method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
    router.add_api_route(
        "/{path:path}",
        proxy_http,
        methods=[_method],
        name=f"proxy_http_{_method.lower()}",
    )


@router.websocket("/{path:path}")
async def proxy_ws(
    websocket: WebSocket,
    container_id: str,
    path: str,
) -> None:
    session_container = websocket.state.dishka_container
    try:
        async with session_container(scope=Scope.REQUEST) as request_container:
            get_browser = await request_container.get(GetBrowserCommand)
            browser = await get_browser(GetBrowserParameters(container_id=container_id))
    except Exception as exc:
        _logger.warning(
            "proxy_ws_browser_failed",
            container_id=container_id,
            error=str(exc),
        )
        await websocket.close(code=1011, reason="Browser not found")
        return

    query = websocket.scope.get("query_string", b"").decode()
    upstream_url = f"ws://{browser.host}:{browser.port}/{path}"
    if query:
        upstream_url += f"?{query}"

    await _touch(session_container, container_id)

    origin = websocket.headers.get("origin")
    protocol_header = websocket.headers.get("sec-websocket-protocol")
    subprotocols = None
    if protocol_header:
        subprotocols = [
            item.strip() for item in protocol_header.split(",") if item.strip()
        ]

    try:
        async with websockets.connect(
            upstream_url,
            max_size=None,
            proxy=None,
            origin=Origin(origin) if origin is not None else None,
            user_agent_header=None,
            subprotocols=(
                [Subprotocol(s) for s in subprotocols]
                if subprotocols is not None
                else None
            ),
        ) as upstream:
            await websocket.accept(subprotocol=upstream.subprotocol)
            await _proxy_ws(
                websocket=websocket,
                upstream=upstream,
                session_container=session_container,
                container_id=container_id,
            )
    except Exception as exc:
        _logger.warning(
            "proxy_ws_failed",
            container_id=container_id,
            error=str(exc),
        )
        if websocket.client_state in (
            WebSocketState.CONNECTING,
            WebSocketState.CONNECTED,
        ):
            await websocket.close(code=1011, reason=f"Upstream failed: {exc}")


async def _touch(session_container: AsyncContainer, container_id: str) -> None:
    try:
        async with session_container(scope=Scope.REQUEST) as request_container:
            touch = await request_container.get(TouchBrowserCommand)
            await touch(TouchBrowserParameters(container_id=container_id))
    except Exception as exc:
        _logger.warning(
            "proxy_touch_failed",
            container_id=container_id,
            error=str(exc),
        )


async def _proxy_ws(
    websocket: WebSocket,
    upstream: ClientConnection,
    session_container: AsyncContainer,
    container_id: str,
) -> None:
    last_touch = time.monotonic()

    async def client_to_upstream() -> None:
        nonlocal last_touch
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is not None:
                await upstream.send(text)
            else:
                data = message.get("bytes")
                if data is not None:
                    await upstream.send(data)
            now = time.monotonic()
            if now - last_touch >= _TOUCH_INTERVAL_SECONDS:
                last_touch = now
                await _touch(session_container, container_id)

    async def upstream_to_client() -> None:
        try:
            async for message in upstream:
                if isinstance(message, str):
                    await websocket.send_text(message)
                else:
                    await websocket.send_bytes(message)
        except ConnectionClosed:
            return

    tasks = [
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        with contextlib.suppress(Exception):
            task.result()

    if upstream.state is not State.CLOSED:
        with contextlib.suppress(Exception):
            await upstream.close()

    if websocket.client_state == WebSocketState.CONNECTED:
        with contextlib.suppress(Exception):
            await websocket.close(
                code=upstream.close_code or 1000,
                reason=upstream.close_reason or "",
            )

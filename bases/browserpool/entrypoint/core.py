import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from browserpool.container_driver import ContainerDriverProvider
from browserpool.database import DatabaseProvider
from browserpool.domain_core import DomainException
from browserpool.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from browserpool.service import ServiceProvider
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, status
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from uvicorn import Config, Server

from .exceptions import (
    CustomHTTPException,
    all_exception_handler,
    custom_http_exception_handler,
    domain_exception_handler,
)
from .routers import (
    browsers_router,
    internal_router,
    node_router,
    proxy_router,
)
from .scheme import ErrorResponse
from .settings import EntrypointSettings


class EntrypointSettingsProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> EntrypointSettings:
        return EntrypointSettings()  # pyright: ignore


class ProxyProvider(Provider):
    @provide(scope=Scope.APP)
    async def http_client(
        self,
        settings: EntrypointSettings,
    ) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            timeout=settings.proxy_timeout_seconds,
            follow_redirects=False,
        ) as client:
            yield client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.dishka_container.close()


async def build_app() -> FastAPI:
    container = make_async_container(
        EntrypointSettingsProvider(),
        ProxyProvider(),
        LoggingSettingsProvider(),
        DatabaseProvider(),
        ContainerDriverProvider(),
        ServiceProvider(),
    )

    entrypoint_settings = await container.get(EntrypointSettings)
    logging_settings = await container.get(LoggingSettings)

    setup_logging(logging_settings, "entrypoint")

    app = FastAPI(
        title=entrypoint_settings.app_name,
        docs_url=entrypoint_settings.api_prefix + "/docs",
        redoc_url=entrypoint_settings.api_prefix + "/redoc",
        openapi_url=entrypoint_settings.api_prefix + "/openapi.json",
        swagger_ui_oauth2_redirect_url=entrypoint_settings.api_prefix
        + "/docs/oauth2-redirect",
        lifespan=lifespan,
        responses={
            status.HTTP_500_INTERNAL_SERVER_ERROR: {
                "model": ErrorResponse,
                "description": "Внутренняя ошибка сервера",
            },
            status.HTTP_401_UNAUTHORIZED: {
                "model": ErrorResponse,
                "description": "Ошибка авторизации",
            },
        },
    )

    setup_dishka(container=container, app=app)
    FastAPIInstrumentor.instrument_app(app)

    app.add_exception_handler(CustomHTTPException, custom_http_exception_handler)
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(Exception, all_exception_handler)

    app.include_router(browsers_router, prefix=entrypoint_settings.methods_prefix)
    app.include_router(node_router, prefix=entrypoint_settings.methods_prefix)
    app.include_router(proxy_router, prefix=entrypoint_settings.methods_prefix)
    app.include_router(internal_router, prefix=entrypoint_settings.methods_prefix)

    app.get("/ping", include_in_schema=False)(lambda: "pong")

    return app


async def run_app() -> None:
    app = await build_app()
    entrypoint_settings: EntrypointSettings = await app.state.dishka_container.get(
        EntrypointSettings
    )

    config = Config(
        app=app,
        host="0.0.0.0",
        port=entrypoint_settings.api_port,
        reload=False,
    )
    server = Server(config)
    await server.serve()


def run() -> None:
    asyncio.run(run_app())

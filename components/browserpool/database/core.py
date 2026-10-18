from collections.abc import AsyncGenerator, AsyncIterable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from dishka import AsyncContainer, Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import URL, event, text
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from .models import BrowserDAO, DAOSession, ReadSession, SandboxDAO, WriteSession
from .settings import DatabaseSettings


class _DAOScope[TSession: DAOSession]:
    def __init__(self, dao_session: TSession) -> None:
        self._dao_session: TSession = dao_session

    def __call__[TDAO](
        self,
        dao_cls: Callable[[TSession], TDAO],
    ) -> TDAO:
        return dao_cls(self._dao_session)

    async def commit(self) -> None:
        await self._dao_session.session.commit()


class DAOFactory:
    def __init__(self, app_container: AsyncContainer) -> None:
        self._app_container: AsyncContainer = app_container

    @asynccontextmanager
    async def __call__[TSession: DAOSession](
        self, dao_session_type: type[TSession]
    ) -> AsyncGenerator[_DAOScope[TSession]]:
        async with self._app_container() as request_container:
            yield _DAOScope[TSession](await request_container.get(dao_session_type))


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> DatabaseSettings:
        return DatabaseSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def database_url(
        self,
        database_settings: DatabaseSettings,
    ) -> URL:
        return URL.create(
            "sqlite+aiosqlite",
            database=database_settings.sqlite_database_path,
        )

    @provide(scope=Scope.APP)
    async def engine(
        self,
        database_url: URL,
        database_settings: DatabaseSettings,
    ) -> AsyncIterable[AsyncEngine]:
        logger = structlog.get_logger("database")
        engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=database_settings.sqlite_pool_size,
            max_overflow=database_settings.sqlite_max_overflow,
            connect_args={
                "timeout": database_settings.sqlite_pool_timeout,
                "check_same_thread": False,
            },
            pool_timeout=database_settings.sqlite_pool_timeout,
        )

        busy_timeout_ms = int(database_settings.sqlite_pool_timeout * 1000)

        def set_sqlite_pragma(
            dbapi_connection: DBAPIConnection, **_kwargs: Any
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

        event.listen(engine.sync_engine, "connect", set_sqlite_pragma, named=True)
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=trace.get_tracer_provider(),
            enable_commenter=True,
            commenter_options={"trace_id": True, "span_id": True},
        )
        logger.info("database_engine_created")
        try:
            yield engine
        finally:
            logger.info("disposing_database_engine")
            await engine.dispose()

    @provide(scope=Scope.APP)
    def session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @provide(scope=Scope.REQUEST)
    async def read_session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[ReadSession]:
        async with session_maker() as session:
            yield ReadSession(session=session)

    @provide(scope=Scope.REQUEST)
    async def write_session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[WriteSession]:
        async with session_maker() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            yield WriteSession(session=session)

    data_access_object_factory: CompositeDependencySource = provide(
        DAOFactory, scope=Scope.APP
    )

    data_access_objects: CompositeDependencySource = provide_all(
        BrowserDAO, SandboxDAO, scope=Scope.REQUEST
    )

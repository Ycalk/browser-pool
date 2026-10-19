from collections.abc import AsyncGenerator, AsyncIterable, Callable
from contextlib import asynccontextmanager
from typing import Any, NewType

import structlog
from dishka import AsyncContainer, Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import URL, event
from sqlalchemy.engine import Connection
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

ReadEngine = NewType("ReadEngine", AsyncEngine)
WriteEngine = NewType("WriteEngine", AsyncEngine)
ReadSessionMaker = NewType("ReadSessionMaker", async_sessionmaker[AsyncSession])
WriteSessionMaker = NewType("WriteSessionMaker", async_sessionmaker[AsyncSession])


class _DAOScope[TSession: DAOSession]:
    def __init__(self, dao_session: TSession) -> None:
        self._dao_session: TSession = dao_session

    def __call__[TDAO](
        self,
        dao_cls: Callable[[TSession], TDAO],
    ) -> TDAO:
        return dao_cls(self._dao_session)


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

    def _create_engine(
        self,
        database_url: URL,
        database_settings: DatabaseSettings,
        *,
        begin_immediate: bool,
    ) -> AsyncEngine:
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

        def set_sqlite_pragma(dbapi_connection: DBAPIConnection, **_kw: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

        event.listen(engine.sync_engine, "connect", set_sqlite_pragma, named=True)

        if begin_immediate:

            def do_begin_immediate(conn: Connection) -> None:
                conn.exec_driver_sql("BEGIN IMMEDIATE")

            event.listen(engine.sync_engine, "begin", do_begin_immediate, named=True)

        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=trace.get_tracer_provider(),
            enable_commenter=True,
            commenter_options={"trace_id": True, "span_id": True},
        )
        return engine

    @provide(scope=Scope.APP)
    async def read_engine(
        self,
        database_url: URL,
        database_settings: DatabaseSettings,
    ) -> AsyncIterable[ReadEngine]:
        logger = structlog.get_logger("database")
        engine = self._create_engine(
            database_url, database_settings, begin_immediate=False
        )
        logger.info("database_read_engine_created")
        try:
            yield ReadEngine(engine)
        finally:
            logger.info("disposing_database_read_engine")
            await engine.dispose()

    @provide(scope=Scope.APP)
    async def write_engine(
        self,
        database_url: URL,
        database_settings: DatabaseSettings,
    ) -> AsyncIterable[WriteEngine]:
        logger = structlog.get_logger("database")
        engine = self._create_engine(
            database_url, database_settings, begin_immediate=True
        )
        logger.info("database_write_engine_created")
        try:
            yield WriteEngine(engine)
        finally:
            logger.info("disposing_database_write_engine")
            await engine.dispose()

    @provide(scope=Scope.APP)
    def read_session_maker(self, read_engine: ReadEngine) -> ReadSessionMaker:
        return ReadSessionMaker(
            async_sessionmaker(
                read_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        )

    @provide(scope=Scope.APP)
    def write_session_maker(self, write_engine: WriteEngine) -> WriteSessionMaker:
        return WriteSessionMaker(
            async_sessionmaker(
                write_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        )

    @provide(scope=Scope.REQUEST)
    async def read_session(
        self, read_session_maker: ReadSessionMaker
    ) -> AsyncIterable[ReadSession]:
        async with read_session_maker() as session, session.begin():
            exc = yield ReadSession(session=session)
            if exc is not None:
                await session.rollback()

    @provide(scope=Scope.REQUEST)
    async def write_session(
        self, write_session_maker: WriteSessionMaker
    ) -> AsyncIterable[WriteSession]:
        async with write_session_maker() as session, session.begin():
            exc = yield WriteSession(session=session)
            if exc is not None:
                await session.rollback()

    data_access_object_factory: CompositeDependencySource = provide(
        DAOFactory, scope=Scope.APP
    )

    data_access_objects: CompositeDependencySource = provide_all(
        BrowserDAO, SandboxDAO, scope=Scope.REQUEST
    )

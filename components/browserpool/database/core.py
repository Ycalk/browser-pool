from collections.abc import AsyncGenerator, AsyncIterable, Callable
from contextlib import asynccontextmanager
from typing import NewType

import structlog
from dishka import Provider, Scope, provide
from dishka.dependency_source import CompositeDependencySource
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import DatabaseSettings

DatabaseUrl = NewType("DatabaseUrl", str)


class _DAOScope:
    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    def __call__[T_DAO](
        self,
        dao_cls: Callable[[AsyncSession], T_DAO],
    ) -> T_DAO:
        return dao_cls(self._session)

    async def commit(self) -> None:
        await self._session.commit()


class DAOFactory:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker: async_sessionmaker[AsyncSession] = session_maker

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[_DAOScope]:
        async with self._session_maker() as session:
            async with session.begin():
                yield _DAOScope(session)


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> DatabaseSettings:
        return DatabaseSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def database_url(
        self,
        database_settings: DatabaseSettings,
    ) -> DatabaseUrl:
        url = (
            f"postgresql+asyncpg://{database_settings.postgres_user}"
            + f":{database_settings.postgres_password}"
            + f"@{database_settings.postgres_host}"
            + f":{database_settings.postgres_port}"
            + f"/{database_settings.postgres_db}"
        )
        return DatabaseUrl(url)

    @provide(scope=Scope.APP)
    async def engine(
        self,
        database_url: DatabaseUrl,
        database_settings: DatabaseSettings,
    ) -> AsyncIterable[AsyncEngine]:
        logger = structlog.get_logger("database")
        engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=database_settings.postgres_pool_size,
            max_overflow=database_settings.postgres_max_overflow,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "timezone": "UTC",
                }
            },
            isolation_level="READ COMMITTED",
        )
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
    async def session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session:
            async with session.begin():
                yield session

    dao_factory: CompositeDependencySource = provide(DAOFactory, scope=Scope.APP)

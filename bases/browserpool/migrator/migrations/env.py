import asyncio
from logging.config import fileConfig

from alembic import context
from browserpool.database import DatabaseProvider
from browserpool.database.core import DatabaseUrl
from browserpool.database.models._base import BaseModel
from browserpool.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from dishka import make_async_container, make_container
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


def register_models() -> list[type[BaseModel]]:
    return []


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    register_models()
    container = make_container(DatabaseProvider(), LoggingSettingsProvider())
    setup_logging(container.get(LoggingSettings), "migrator")

    url = container.get(DatabaseUrl)
    context.configure(
        url=url,
        target_metadata=BaseModel.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=BaseModel.metadata,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    register_models()
    container = make_async_container(DatabaseProvider(), LoggingSettingsProvider())
    setup_logging(await container.get(LoggingSettings), "migrator")
    connectable = await container.get(AsyncEngine)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

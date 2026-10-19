from collections.abc import AsyncIterator

import pytest_asyncio
from browserpool.database import (
    BrowserDAO,
    DatabaseProvider,
    ReadSession,
    SandboxDAO,
    WriteSession,
)
from browserpool.database.core import WriteEngine
from browserpool.database.models import BaseModel
from dishka import AsyncContainer, make_async_container
from sqlalchemy import delete, inspect
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture(scope="session")
async def app_container() -> AsyncIterator[AsyncContainer]:
    container = make_async_container(DatabaseProvider())
    try:
        yield container
    finally:
        await container.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(app_container: AsyncContainer):
    write_engine: AsyncEngine = await app_container.get(WriteEngine)
    async with write_engine.begin() as conn:
        existing = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
        for table in BaseModel.metadata.sorted_tables:
            if table.fullname in existing:
                await conn.execute(delete(table))


@pytest_asyncio.fixture
async def request_container(
    app_container: AsyncContainer,
) -> AsyncIterator[AsyncContainer]:
    async with app_container() as request_container:
        yield request_container


@pytest_asyncio.fixture
async def browser_read_dao(
    request_container: AsyncContainer,
) -> BrowserDAO[ReadSession]:
    return await request_container.get(BrowserDAO[ReadSession])


@pytest_asyncio.fixture
async def browser_write_dao(
    request_container: AsyncContainer,
) -> BrowserDAO[WriteSession]:
    return await request_container.get(BrowserDAO[WriteSession])


@pytest_asyncio.fixture
async def sandbox_read_dao(
    request_container: AsyncContainer,
) -> SandboxDAO[ReadSession]:
    return await request_container.get(SandboxDAO[ReadSession])


@pytest_asyncio.fixture
async def sandbox_write_dao(
    request_container: AsyncContainer,
) -> SandboxDAO[WriteSession]:
    return await request_container.get(SandboxDAO[WriteSession])

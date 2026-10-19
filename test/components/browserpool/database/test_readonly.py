"""ReadSession-backed DAOs must reject every mutating operation."""

import pytest
from browserpool.database import (
    Browser,
    BrowserDAO,
    ReadSession,
    Sandbox,
    SandboxCreateParameters,
    SandboxDAO,
    WriteSession,
)


async def test_read_session_create_raises(
    sandbox_read_dao: SandboxDAO[ReadSession],
) -> None:
    with pytest.raises(RuntimeError, match="readonly cannot create"):
        await sandbox_read_dao.create(
            SandboxCreateParameters(network_id="x", network_name="x", index=0)
        )


async def test_read_session_bulk_create_raises(
    sandbox_read_dao: SandboxDAO[ReadSession],
) -> None:
    with pytest.raises(RuntimeError, match="readonly cannot create"):
        await sandbox_read_dao.bulk_create(
            [SandboxCreateParameters(network_id="x", network_name="x", index=0)]
        )


async def test_read_session_save_raises(
    browser_read_dao: BrowserDAO[ReadSession],
) -> None:
    """save() rejects even if the object is constructed manually."""
    obj = Browser(
        container_id="x",
        network_id="x",
        variant="v",
        host="h",
        port=1,
        idle_ttl_seconds=1,
    )
    with pytest.raises(RuntimeError, match="readonly cannot save"):
        await browser_read_dao.save(obj)


async def test_read_session_delete_raises(
    sandbox_read_dao: SandboxDAO[ReadSession],
) -> None:
    obj = Sandbox(network_id="x", network_name="x", index=0)
    with pytest.raises(RuntimeError, match="readonly cannot delete"):
        await sandbox_read_dao.delete(obj)


async def test_write_session_allows_create(
    sandbox_write_dao: SandboxDAO[WriteSession],
) -> None:
    """Sanity check: the same operations succeed on a WriteSession."""
    created = await sandbox_write_dao.create(
        SandboxCreateParameters(network_id="net-allow", network_name="a", index=0)
    )
    assert created.network_id == "net-allow"
    assert await sandbox_write_dao.exists_by_id("net-allow") is True


async def test_read_session_queries_allowed(
    sandbox_read_dao: SandboxDAO[ReadSession],
) -> None:
    """ReadSession must allow find_by_id, count, exists_by_id."""
    assert await sandbox_read_dao.find_by_id("missing") is None
    assert await sandbox_read_dao.count() >= 0
    assert await sandbox_read_dao.exists_by_id("missing") is False

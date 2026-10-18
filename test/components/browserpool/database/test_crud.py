from collections.abc import Sequence
from enum import StrEnum
from typing import override

import pytest
from browserpool.database import (
    Browser,
    BrowserCreateParameters,
    BrowserDAO,
    BrowserLoadEnum,
    ReadSession,
    Sandbox,
    SandboxCreateParameters,
    SandboxDAO,
    SandboxLoadEnum,
    WriteSession,
)
from browserpool.database.models._base import BaseDAO, BaseModel
from dishka import AsyncContainer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.interfaces import ORMOption


def test_dao_model_attribute_resolved_at_class_creation() -> None:
    """__init_subclass__ populates .model from the 5 generic parameters."""
    assert BrowserDAO.model is Browser
    assert SandboxDAO.model is Sandbox


def test_load_mapper_covers_all_enum_members() -> None:
    """Every LoadEnum member must map to an ORM option."""
    assert set(BrowserDAO._load_mapper()) == set(BrowserLoadEnum)  # pyright: ignore[reportPrivateUsage]
    assert set(SandboxDAO._load_mapper()) == set(SandboxLoadEnum)  # pyright: ignore[reportPrivateUsage]


def test_init_subclass_rejects_non_basemodel() -> None:
    """A DAO with a non-BaseModel TModel fails at class creation."""

    class GoodEnum(StrEnum):
        A = "a"

    with pytest.raises(TypeError, match="Unexpected type for TModel"):

        class BadModelDAO(BaseDAO[object, object, int, GoodEnum, dict]):  # type: ignore[valid-type]
            @classmethod
            @override
            def _load_mapper(cls) -> dict[GoodEnum, ORMOption | Sequence[ORMOption]]:
                return {}


def test_init_subclass_rejects_non_strenum() -> None:
    """A DAO with a non-StrEnum TLoadEnum fails at class creation."""

    class FakeModel(BaseModel):
        __tablename__: str = "fake_enum_test_crud"
        id: Mapped[int] = mapped_column(primary_key=True)

    with pytest.raises(TypeError, match="Unexpected type for TLoadEnum"):

        class BadEnumDAO(BaseDAO[object, FakeModel, int, object, dict]):  # type: ignore[valid-type]
            @classmethod
            @override
            def _load_mapper(cls) -> dict[object, ORMOption | Sequence[ORMOption]]:
                return {}


async def test_create_and_find_by_id_roundtrip(
    sandbox_write_dao: SandboxDAO[WriteSession],
) -> None:
    """A sandbox written via WriteSession is visible inside the same transaction."""
    created = await sandbox_write_dao.create(
        SandboxCreateParameters(network_id="net-create-1", network_name="roundtrip")
    )
    assert created.network_id == "net-create-1"
    assert created.network_name == "roundtrip"
    assert created.active is True

    found = await sandbox_write_dao.find_by_id("net-create-1")
    assert found is not None
    assert found.network_name == "roundtrip"


async def test_count_increments_after_create(
    sandbox_write_dao: SandboxDAO[WriteSession],
) -> None:
    """count() reflects inserts within the same write transaction."""
    initial = await sandbox_write_dao.count()
    await sandbox_write_dao.create(
        SandboxCreateParameters(network_id="net-count", network_name="n")
    )
    after = await sandbox_write_dao.count()
    assert after == initial + 1


async def test_exists_by_id(sandbox_write_dao: SandboxDAO[WriteSession]) -> None:
    """exists_by_id returns True for present, False for absent."""
    assert await sandbox_write_dao.exists_by_id("missing") is False
    await sandbox_write_dao.create(
        SandboxCreateParameters(network_id="net-exists", network_name="x")
    )
    assert await sandbox_write_dao.exists_by_id("net-exists") is True


async def test_bulk_create(sandbox_write_dao: SandboxDAO[WriteSession]) -> None:
    """bulk_create inserts all rows and returns them."""
    params = [
        SandboxCreateParameters(network_id=f"bulk-{i}", network_name=f"b{i}")
        for i in range(3)
    ]
    rows = await sandbox_write_dao.bulk_create(params)
    assert len(rows) == 3
    assert {r.network_id for r in rows} == {"bulk-0", "bulk-1", "bulk-2"}


async def test_bulk_create_empty_is_noop(
    sandbox_write_dao: SandboxDAO[WriteSession],
) -> None:
    assert await sandbox_write_dao.bulk_create([]) == []


async def test_delete(sandbox_write_dao: SandboxDAO[WriteSession]) -> None:
    """delete removes the object and flushes."""
    created = await sandbox_write_dao.create(
        SandboxCreateParameters(network_id="net-del", network_name="d")
    )
    assert await sandbox_write_dao.exists_by_id("net-del") is True
    await sandbox_write_dao.delete(created)
    assert await sandbox_write_dao.exists_by_id("net-del") is False


async def test_find_by_id_missing_returns_none(
    sandbox_read_dao: SandboxDAO[ReadSession],
) -> None:
    assert await sandbox_read_dao.find_by_id("nope") is None


async def test_persisted_write_visible_to_read_after_scope_exit(
    request_container: AsyncContainer,
) -> None:
    """Data written in one request scope is visible to a fresh read scope.

    The transaction commits on scope exit; a new read session sees it.
    """
    async with request_container:
        sd_w = await request_container.get(SandboxDAO[WriteSession])
        await sd_w.create(
            SandboxCreateParameters(network_id="net-persist", network_name="p")
        )
    async with request_container:
        sd_r = await request_container.get(SandboxDAO[ReadSession])
        found = await sd_r.find_by_id("net-persist")
        assert found is not None
        assert found.network_name == "p"


async def test_find_by_id_with_includes_loads_relationship(
    request_container: AsyncContainer,
) -> None:
    """find_by_id with SandboxLoadEnum.BROWSERS eagerly loads browsers."""
    async with request_container:
        sd_w = await request_container.get(SandboxDAO[WriteSession])
        await sd_w.create(
            SandboxCreateParameters(network_id="net-inc", network_name="parent")
        )
        bd_w = await request_container.get(BrowserDAO[WriteSession])
        await bd_w.create(
            BrowserCreateParameters(
                container_id="br-1",
                network_id="net-inc",
                variant="camoufox",
                host="127.0.0.1",
                port=9999,
                idle_ttl_seconds=60,
            )
        )

    async with request_container:
        sd_r = await request_container.get(SandboxDAO[ReadSession])
        found = await sd_r.find_by_id("net-inc", includes=[SandboxLoadEnum.BROWSERS])
    assert found is not None
    assert len(found.browsers) == 1
    assert found.browsers[0].container_id == "br-1"


async def test_cascade_delete_browsers(
    request_container: AsyncContainer,
) -> None:
    """Deleting a sandbox cascades to its browsers (FK ondelete CASCADE)."""
    async with request_container:
        sd_w = await request_container.get(SandboxDAO[WriteSession])
        await sd_w.create(
            SandboxCreateParameters(network_id="net-casc", network_name="c")
        )
        bd_w = await request_container.get(BrowserDAO[WriteSession])
        await bd_w.create(
            BrowserCreateParameters(
                container_id="br-casc",
                network_id="net-casc",
                variant="v",
                host="h",
                port=1,
                idle_ttl_seconds=10,
            )
        )
        sandbox = await sd_w.find_by_id("net-casc", includes=[SandboxLoadEnum.BROWSERS])
        assert sandbox is not None
        await sd_w.delete(sandbox)
        assert await bd_w.find_by_id("br-casc") is None

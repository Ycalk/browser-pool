from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import NotRequired, TypedDict, override

from sqlalchemy import Boolean, ForeignKey, Integer, Text, select
from sqlalchemy.orm import Mapped, joinedload, mapped_column, relationship
from sqlalchemy.orm.interfaces import ORMOption

from ._base import BaseDAO, BaseModel, DAOSession, IntUnixTimestamp
from .sandbox import Sandbox


class Browser(BaseModel):
    __tablename__: str = "browser"

    container_id: Mapped[str] = mapped_column(Text, primary_key=True)
    network_id: Mapped[str] = mapped_column(
        ForeignKey("sandbox.network_id", ondelete="CASCADE"), index=True
    )
    variant: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    port: Mapped[int] = mapped_column(Integer)
    last_touched_at: Mapped[datetime] = mapped_column(
        IntUnixTimestamp, default=lambda: datetime.now(UTC)
    )
    idle_ttl_seconds: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    sandbox: Mapped[Sandbox] = relationship(back_populates="browsers")


class BrowserCreateParameters(TypedDict):
    container_id: str
    network_id: str
    variant: str
    host: str
    port: int
    last_touched_at: NotRequired[datetime]
    idle_ttl_seconds: int
    active: NotRequired[bool]
    created_at: NotRequired[datetime]


class BrowserLoadEnum(StrEnum):
    SANDBOX = "sandbox"


class BrowserDAO[TSession: DAOSession](
    BaseDAO[TSession, Browser, str, BrowserLoadEnum, BrowserCreateParameters]
):
    @classmethod
    @override
    def _load_mapper(cls) -> dict[BrowserLoadEnum, ORMOption | Sequence[ORMOption]]:
        return {BrowserLoadEnum.SANDBOX: joinedload(Browser.sandbox)}

    async def find_all(
        self, *, includes: Sequence[BrowserLoadEnum] | None = None
    ) -> Sequence[Browser]:
        stmt = select(self.model).order_by(self.model.created_at)
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_active(
        self, *, includes: Sequence[BrowserLoadEnum] | None = None
    ) -> Sequence[Browser]:
        stmt = (
            select(self.model)
            .where(self.model.active.is_(True))
            .order_by(self.model.created_at)
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_expired(
        self,
        *,
        includes: Sequence[BrowserLoadEnum] | None = None,
    ) -> Sequence[Browser]:
        now = datetime.now(UTC)
        stmt = (
            select(self.model)
            .where(
                self.model.active.is_(True),
                (self.model.last_touched_at + self.model.idle_ttl_seconds)
                < int(now.timestamp()),
            )
            .order_by(self.model.created_at)
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_active_in_inactive_sandboxes(
        self,
        *,
        includes: Sequence[BrowserLoadEnum] | None = None,
    ) -> Sequence[Browser]:
        stmt = (
            select(self.model)
            .join(Sandbox)
            .where(
                self.model.active.is_(True),
                Sandbox.active.is_(False),
            )
            .order_by(self.model.created_at)
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, NotRequired, TypedDict, override

from sqlalchemy import Boolean, Integer, Text, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from sqlalchemy.orm.interfaces import ORMOption

from ._base import BaseDAO, BaseModel, DAOSession

if TYPE_CHECKING:
    from .browser import Browser


class Sandbox(BaseModel):
    __tablename__: str = "sandbox"

    network_id: Mapped[str] = mapped_column(Text, primary_key=True)
    network_name: Mapped[str] = mapped_column(Text)
    index: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    browsers: Mapped[list[Browser]] = relationship(
        back_populates="sandbox", cascade="all, delete-orphan", passive_deletes=True
    )


class SandboxCreateParameters(TypedDict):
    network_id: str
    network_name: str
    index: int
    active: NotRequired[bool]
    created_at: NotRequired[datetime]


class SandboxLoadEnum(StrEnum):
    BROWSERS = "browsers"


class SandboxDAO[TSession: DAOSession](
    BaseDAO[TSession, Sandbox, str, SandboxLoadEnum, SandboxCreateParameters]
):
    @classmethod
    @override
    def _load_mapper(cls) -> dict[SandboxLoadEnum, ORMOption | Sequence[ORMOption]]:
        return {SandboxLoadEnum.BROWSERS: selectinload(Sandbox.browsers)}

    async def find_active_without_browsers(
        self, *, includes: Sequence[SandboxLoadEnum] | None = None
    ) -> Sequence[Sandbox]:
        stmt = (
            select(self.model)
            .where(self.model.active.is_(True), ~self.model.browsers.any())
            .order_by(self.model.index)
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_all(
        self, *, includes: Sequence[SandboxLoadEnum] | None = None
    ) -> Sequence[Sandbox]:
        stmt = select(self.model).order_by(self.model.index)
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_active(
        self, *, includes: Sequence[SandboxLoadEnum] | None = None
    ) -> Sequence[Sandbox]:
        stmt = (
            select(self.model)
            .where(self.model.active.is_(True))
            .order_by(self.model.index)
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def find_active_by_index(self, index: int) -> Sandbox | None:
        stmt = select(self.model).where(
            self.model.active.is_(True), self.model.index == index
        )
        result = await self._session.scalars(stmt)
        return result.first()

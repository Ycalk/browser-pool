from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, NotRequired, TypedDict, override

from sqlalchemy import Boolean, Text, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from sqlalchemy.orm.interfaces import ORMOption

from ._base import BaseDAO, BaseModel, DAOSession

if TYPE_CHECKING:
    from .browser import Browser


class Sandbox(BaseModel):
    __tablename__: str = "sandbox"

    network_id: Mapped[str] = mapped_column(Text, primary_key=True)
    network_name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    browsers: Mapped[list[Browser]] = relationship(
        back_populates="sandbox", cascade="all, delete-orphan", passive_deletes=True
    )


class SandboxCreateParameters(TypedDict):
    network_id: str
    network_name: str
    active: NotRequired[bool]


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
        self, includes: Sequence[SandboxLoadEnum] | None = None
    ) -> Sequence[Sandbox]:
        stmt = select(self.model).where(
            self.model.active.is_(True), ~self.model.browsers.any()
        )
        if includes is not None:
            stmt = stmt.options(*self.get_options(includes))
        result = await self._session.scalars(stmt)
        return result.all()

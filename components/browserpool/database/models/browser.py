from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, NotRequired, TypedDict, override

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, joinedload, mapped_column, relationship
from sqlalchemy.orm.interfaces import ORMOption

from ._base import BaseDAO, BaseModel, DAOSession, IntUnixTimestamp

if TYPE_CHECKING:
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


class BrowserLoadEnum(StrEnum):
    SANDBOX = "sandbox"


class BrowserDAO[TSession: DAOSession](
    BaseDAO[TSession, Browser, str, BrowserLoadEnum, BrowserCreateParameters]
):
    @classmethod
    @override
    def _load_mapper(cls) -> dict[BrowserLoadEnum, ORMOption | Sequence[ORMOption]]:
        return {BrowserLoadEnum.SANDBOX: joinedload(Browser.sandbox)}

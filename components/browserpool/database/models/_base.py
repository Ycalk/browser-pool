from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, cast, get_args, get_origin

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.types import TIMESTAMP


class BaseModel(AsyncAttrs, DeclarativeBase):
    __abstract__: bool = True
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BaseDAO[
    TModel: BaseModel,
    TId,
    TLoadEnum: StrEnum,
    TCreateParameters: Mapping[str, Any],
](ABC):
    model: type[TModel]

    def __init__(self, session: AsyncSession):
        self._session: AsyncSession = session

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            origin = get_origin(base)
            if not (isinstance(origin, type) and issubclass(origin, BaseDAO)):
                continue
            args = get_args(base)
            if len(args) != 4:
                continue

            model_type, __, load_enum_type, _ = args
            if not (isinstance(model_type, type) and issubclass(model_type, BaseModel)):
                raise TypeError(
                    f"{cls.__name__}: Unexpected type for TModel. "
                    + f"Got: {model_type.__name__} ({type(model_type)})"
                )
            cls.model = cast(type[TModel], model_type)

            if not (
                isinstance(load_enum_type, type) and issubclass(load_enum_type, StrEnum)
            ):
                raise TypeError(
                    f"{cls.__name__}: Unexpected type for TLoadEnum. "
                    + f"Got: {load_enum_type.__name__} ({type(load_enum_type)})"
                )
            load_mapper = cls._load_mapper()
            for member in load_enum_type:
                if member not in load_mapper:
                    raise ValueError(f"Cannot find {member} key in _load_mapper")

            return

        if not hasattr(cls, "model") or not hasattr(cls, "_primary_key_column"):
            raise TypeError(
                f"Failed to initialize {cls.__name__}. Not enough generic parameters"
            )

    @classmethod
    @abstractmethod
    def _load_mapper(cls) -> dict[TLoadEnum, ORMOption | Sequence[ORMOption]]:
        return {}

    def get_options(self, includes: Sequence[TLoadEnum]) -> Sequence[ORMOption]:
        options: list[ORMOption] = []
        for include in includes:
            option = self._load_mapper().get(include)
            if option is None:
                raise ValueError(f"Invalid include option: {include}")
            if isinstance(option, Sequence):
                options.extend(option)
            else:
                options.append(option)
        return options

    async def save(self, obj: TModel) -> TModel:
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(
            obj,
            attribute_names=[c.key for c in obj.__table__.columns],
        )
        return obj

    async def delete(self, obj: TModel) -> None:
        await self._session.delete(obj)
        await self._session.flush()

    async def find_by_id(
        self, id: TId, includes: Sequence[TLoadEnum] | None = None
    ) -> TModel | None:
        return await self._session.get(
            self.model,
            id,
            options=self.get_options(includes) if includes is not None else None,
            populate_existing=includes is not None,
        )

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def exists_by_id(self, id: TId) -> bool:
        return await self.find_by_id(id) is not None

    async def bulk_create(self, parameters: list[TCreateParameters]) -> list[TModel]:
        if len(parameters) == 0:
            return []

        stmt = insert(self.model).returning(self.model)
        result = await self._session.scalars(
            stmt, [dict(model_parameters) for model_parameters in parameters]
        )
        return list(result.all())

    async def create(self, parameters: TCreateParameters) -> TModel:
        obj = self.model(**dict(parameters))
        await self.save(obj)
        return obj

    async def commit(self) -> None:
        await self._session.commit()

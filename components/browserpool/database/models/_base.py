from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast, final, get_args, get_origin, override

from sqlalchemy import BigInteger, TypeDecorator, func, insert, select
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.sql.type_api import TypeEngine


class IntUnixTimestamp(TypeDecorator[datetime]):
    impl: TypeEngine[Any] | type[TypeEngine[Any]] = BigInteger
    cache_ok: bool | None = True

    @override
    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return int(value.timestamp())
        if isinstance(value, (int, float)):
            return int(value)

        raise TypeError(f"Expected datetime or int, got {type(value)}")

    @override
    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return datetime.fromtimestamp(value, tz=UTC)


class DAOSession(ABC):
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session


@final
class ReadSession(DAOSession):
    pass


@final
class WriteSession(DAOSession):
    pass


class BaseModel(AsyncAttrs, DeclarativeBase):
    __abstract__: bool = True
    created_at: Mapped[datetime] = mapped_column(
        IntUnixTimestamp, default=lambda: datetime.now(UTC)
    )


class BaseDAO[
    TSession: DAOSession,
    TModel: BaseModel,
    TId,
    TLoadEnum: StrEnum,
    TCreateParameters: Mapping[str, Any],
](ABC):
    model: type[TModel]

    def __init__(self, dao_session: TSession):
        self._session: AsyncSession = dao_session.session
        if not isinstance(dao_session, (ReadSession, WriteSession)):
            raise TypeError(
                f"Unexpected session type. Got: {dao_session.__class__.__name__}. "
                + "Expect: ReadSession or WriteSession"
            )
        self._readonly: bool = isinstance(dao_session, ReadSession)

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            origin = get_origin(base)
            if not (isinstance(origin, type) and issubclass(origin, BaseDAO)):
                continue
            args = get_args(base)
            if len(args) != 5:
                continue

            ___, model_type, __, load_enum_type, _ = args
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
            return

        raise TypeError(
            f"Failed to initialize {cls.__name__}. Not enough generic parameters"
        )

    @classmethod
    @abstractmethod
    def _load_mapper(cls) -> dict[TLoadEnum, ORMOption | Sequence[ORMOption]]: ...

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
        if self._readonly:
            raise RuntimeError("The session is readonly cannot save")

        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(
            obj,
            attribute_names=[c.key for c in obj.__table__.columns],
        )
        return obj

    async def delete(self, obj: TModel) -> None:
        if self._readonly:
            raise RuntimeError("The session is readonly cannot delete")

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
        if self._readonly:
            raise RuntimeError("The session is readonly cannot create")

        if len(parameters) == 0:
            return []

        stmt = insert(self.model).returning(self.model)
        result = await self._session.scalars(
            stmt, [dict(model_parameters) for model_parameters in parameters]
        )
        return list(result.all())

    async def create(self, parameters: TCreateParameters) -> TModel:
        if self._readonly:
            raise RuntimeError("The session is readonly cannot create")

        obj = self.model(**dict(parameters))
        await self.save(obj)
        return obj

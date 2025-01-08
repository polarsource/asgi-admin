from collections.abc import Sequence
from typing import Any, ClassVar, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.mapper import Mapper

from asgi_admin.repository import RepositoryProtocol

Model = TypeVar("Model", bound=object)
ModelMapper = Mapper[Model]


class RepositoryBase(RepositoryProtocol[Model]):
    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, offset: int, limit: int) -> Sequence[Model]:
        statement = select(self.model).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def create(self, item: Model, *, autoflush: bool = True) -> Model:
        self.session.add(item)
        if autoflush:
            await self.session.flush()
        return item

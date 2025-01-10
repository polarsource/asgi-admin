from collections.abc import Iterable, Sequence
from typing import Any, ClassVar, TypeVar, Union

from sqlalchemy import (
    ColumnExpressionArgument,
    Select,
    String,
    asc,
    cast,
    desc,
    func,
    or_,
    over,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.mapper import Mapper

from asgi_admin.repository import RepositoryProtocol, Sorting, SortingOrder

Model = TypeVar("Model", bound=object)
ModelMapper = Mapper[Model]


class RepositoryBase(RepositoryProtocol[Model]):
    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        sorting: Sorting,
        offset: int,
        limit: int,
        *,
        query: Union[str, None] = None,
        query_fields: Union[Iterable[str], None] = None,
    ) -> tuple[int, Sequence[Model]]:
        statement = self.get_base_select()

        if query is not None and query_fields is not None:
            clauses: list[ColumnExpressionArgument[bool]] = []
            for query_field in query_fields:
                clauses.append(
                    cast(getattr(self.model, query_field), String).ilike(f"%{query}%")
                )
            statement = statement.where(or_(*clauses))

        for field, order in sorting:
            order_function = asc if order == SortingOrder.ASC else desc
            statement = statement.order_by(order_function(getattr(self.model, field)))

        paginated_statement: Select[tuple[Model, int]] = (
            statement.add_columns(over(func.count())).limit(limit).offset(offset)
        )
        results = await self.session.stream(paginated_statement)

        items: list[Model] = []
        count = 0
        async for result in results:
            item, count = result._tuple()
            items.append(item)

        return count, items

    async def get_by_id(self, id: Any) -> Union[Model, None]:
        statement = self.get_base_select().where(self.model.id == id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def update(
        self, item: Model, data: dict[str, Any], *, autoflush: bool = True
    ) -> Model:
        for key, value in data.items():
            setattr(item, key, value)
        if autoflush:
            await self.session.flush()
        return item

    async def create(self, item: Model, *, autoflush: bool = True) -> Model:
        self.session.add(item)
        if autoflush:
            await self.session.flush()
        return item

    def get_base_select(self) -> Select[tuple[Model]]:
        return select(self.model)

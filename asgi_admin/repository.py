from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any, Protocol, TypeVar, Union

from typing_extensions import TypeAlias

Model = TypeVar("Model")
IDType = TypeVar("IDType")


class SortingOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


Sorting: TypeAlias = Sequence[tuple[str, SortingOrder]]


class RepositoryProtocol(Protocol[Model]):
    async def list(
        self,
        sorting: Sorting,
        offset: int,
        limit: int,
        *,
        query: Union[str, None] = None,
        query_fields: Union[Iterable[str], None] = None,
    ) -> tuple[int, Sequence[Model]]: ...

    async def get_by_id(self, id: Any) -> Union[Model, None]: ...

    async def update(self, item: Model, data: dict[str, Any]) -> Model: ...

    async def create(self, item: Model) -> Model: ...

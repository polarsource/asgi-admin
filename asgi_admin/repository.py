from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Protocol, TypeVar, Union

from typing_extensions import TypeAlias

Model = TypeVar("Model")


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

    async def create(self, item: Model) -> Model: ...

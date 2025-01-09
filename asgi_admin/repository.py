from collections.abc import Sequence
from enum import Enum
from typing import Protocol, TypeVar

from typing_extensions import TypeAlias

Model = TypeVar("Model")


class SortingOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


Sorting: TypeAlias = Sequence[tuple[str, SortingOrder]]


class RepositoryProtocol(Protocol[Model]):
    async def paginate(
        self, sorting: Sorting, offset: int, limit: int
    ) -> tuple[int, Sequence[Model]]: ...

    async def create(self, item: Model) -> Model: ...

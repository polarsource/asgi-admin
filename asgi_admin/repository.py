from collections.abc import Sequence
from typing import Protocol, TypeVar

Model = TypeVar("Model")


class RepositoryProtocol(Protocol[Model]):
    async def list(self, offset: int, limit: int) -> Sequence[Model]: ...

    async def create(self, item: Model) -> Model: ...

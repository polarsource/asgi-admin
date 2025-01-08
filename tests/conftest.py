import dataclasses
import datetime
from collections.abc import Sequence
from typing import Union

from starlette.requests import Request

from asgi_admin.app import AdminBase
from asgi_admin.repository import RepositoryProtocol
from asgi_admin.views import ModelView


@dataclasses.dataclass
class MyModel:
    id: str
    label: str
    created_at: datetime.datetime


class MyModelRepository(RepositoryProtocol[MyModel]):
    def __init__(self, items: Union[dict[str, MyModel], None] = None) -> None:
        if items is None:
            items = {
                f"item_{i}": MyModel(
                    id=f"item_{i}",
                    label=f"Item {i}",
                    created_at=datetime.datetime.now(),
                )
                for i in range(10)
            }
        self._items = items

    async def list(self, offset: int, limit: int) -> Sequence[MyModel]:
        return list(self._items.values())[offset : offset + limit]

    async def create(self, item: MyModel) -> MyModel:
        self._items[item.id] = item
        return item


class MyModelView(ModelView[MyModel]):
    model = MyModel

    async def get_repository(self, request: Request) -> MyModelRepository:
        return MyModelRepository()


class MyAdmin(AdminBase):
    views = [MyModelView()]

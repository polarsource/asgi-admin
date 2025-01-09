import dataclasses
import datetime
from collections.abc import Sequence
from operator import attrgetter
from typing import Union

from starlette.applications import Starlette
from starlette.requests import Request

from asgi_admin.admin import AdminBase
from asgi_admin.repository import RepositoryProtocol, Sorting, SortingOrder
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

    async def paginate(
        self, sorting: Sorting, offset: int, limit: int
    ) -> tuple[int, Sequence[MyModel]]:
        items = list(self._items.values())
        for field, way in reversed(sorting):
            items.sort(key=attrgetter(field), reverse=way == SortingOrder.DESC)
        return len(items), items[offset : offset + limit]

    async def create(self, item: MyModel) -> MyModel:
        self._items[item.id] = item
        return item


class MyModelView(ModelView[MyModel]):
    model = MyModel
    field_labels = {"id": "ID", "label": "Label", "created_at": "Created At"}
    list_fields = ("id", "label", "created_at")

    async def get_repository(self, request: Request) -> MyModelRepository:
        return MyModelRepository()


class MyAdmin(AdminBase):
    views = [MyModelView()]


app = Starlette()
app.mount("/admin", MyAdmin())

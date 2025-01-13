import dataclasses
import datetime
from collections.abc import AsyncIterator, Iterable, Sequence
from operator import attrgetter
from typing import Any, Union

from starlette.applications import Starlette
from starlette.requests import Request
from wtforms import StringField, validators

from asgi_admin.repository import RepositoryProtocol, Sorting, SortingOrder
from asgi_admin.viewsets import AdminViewSet, ModelViewSet


@dataclasses.dataclass
class MyModel:
    id: str
    label: str
    created_at: datetime.datetime


ITEMS = {
    f"item_{i}": MyModel(
        id=f"item_{i}",
        label=f"Item {i}",
        created_at=datetime.datetime.now(),
    )
    for i in range(10)
}


class MyModelRepository(RepositoryProtocol[MyModel]):
    def __init__(self, items: dict[str, MyModel] = ITEMS) -> None:
        self._items = items

    async def list(
        self,
        sorting: Sorting,
        offset: int,
        limit: int,
        *,
        query: Union[str, None] = None,
        query_fields: Union[Iterable[str], None] = None,
    ) -> tuple[int, Sequence[MyModel]]:
        # Filtering
        def _filter_function(item: MyModel) -> bool:
            if query is None or not query_fields:
                return True
            for query_field in query_fields:
                if query.lower() in str(getattr(item, query_field)).lower():
                    return True
            return False

        items = [item for item in list(self._items.values()) if _filter_function(item)]

        # Sorting
        for field, way in reversed(sorting):
            items.sort(key=attrgetter(field), reverse=way == SortingOrder.DESC)

        # Offset and limit
        return len(items), items[offset : offset + limit]

    async def get_by_id(self, id: str) -> Union[MyModel, None]:
        return self._items.get(id)

    async def update(self, item: MyModel, data: dict[str, Any]) -> MyModel:
        self._items[item.id] = dataclasses.replace(item, **data)
        return self._items[item.id]

    async def create(self, item: MyModel) -> MyModel:
        self._items[item.id] = item
        return item


async def get_my_model_repository(request: Request) -> AsyncIterator[MyModelRepository]:
    yield MyModelRepository()


my_model_viewset = ModelViewSet[MyModel](
    name="my_model",
    title="My Model",
    get_repository=get_my_model_repository,
    pk_getter=attrgetter("id"),
    item_title_getter=lambda _, i: i.label,
    list_fields=(
        ("id", "ID"),
        ("label", "Label"),
        ("created_at", "Created At"),
    ),
    list_query_fields=("id", "label"),
    edit_fields=(
        (
            "label",
            StringField(
                "Label",
                description="The label of the item",
                validators=[validators.InputRequired(), validators.Length(min=3)],
            ),
        ),
    ),
)

admin = AdminViewSet(
    viewsets={
        "/my-model": my_model_viewset,
    }
)


app = Starlette()
app.mount("/admin", admin.router)

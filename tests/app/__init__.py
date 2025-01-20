import dataclasses
import datetime
import functools
from collections.abc import AsyncIterator, Iterable, Sequence
from operator import attrgetter
from typing import Any, Union

from jinja2 import PackageLoader
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import TypeAlias
from wtforms import StringField, validators

from asgi_admin.repository import RepositoryProtocol, Sorting, SortingOrder
from asgi_admin.templating import Renderer
from asgi_admin.views import (
    AdminViewGroup,
    AdminViewIndex,
    ModelView,
    ModelViewEdit,
    ModelViewGroup,
    ModelViewList,
    ViewBase,
)


@dataclasses.dataclass
class MyModel:
    id: str
    label: str
    created_at: datetime.datetime


class MyModelRepository(RepositoryProtocol[MyModel]):
    def __init__(self, items: dict[str, MyModel]) -> None:
        self._items = items

    def get_pk(self, item: MyModel) -> str:
        return item.id

    def get_title(self, item: MyModel) -> str:
        return item.label

    async def list(
        self,
        sorting: Sorting,
        offset: int,
        limit: int,
        *,
        query: Union[str, None] = None,
        query_fields: Union[Iterable[str], None] = None,
    ) -> tuple[int, Sequence[MyModel]]:
        # Queryin
        def _query_function(item: MyModel) -> bool:
            if query is None or not query_fields:
                return True
            for query_field in query_fields:
                if query.lower() in str(getattr(item, query_field)).lower():
                    return True
            return False

        items = [item for item in list(self._items.values()) if _query_function(item)]

        # Sorting
        for field, way in reversed(sorting):
            items.sort(key=attrgetter(field), reverse=way == SortingOrder.DESC)

        # Offset and limit
        return len(items), items[offset : offset + limit]

    async def get_by_pk(self, pk: str) -> Union[MyModel, None]:
        return self._items.get(pk)

    async def update(self, item: MyModel, data: dict[str, Any]) -> MyModel:
        self._items[item.id] = dataclasses.replace(item, **data)
        return self._items[item.id]

    async def create(self, item: MyModel) -> MyModel:
        self._items[item.id] = item
        return item


MyModelMapping: TypeAlias = dict[str, MyModel]


async def get_my_model_repository(
    items: MyModelMapping, request: Request
) -> AsyncIterator[MyModelRepository]:
    yield MyModelRepository(items)


def create_admin(items: MyModelMapping) -> ViewBase:
    class ModelViewCustom(ModelView[MyModel]):
        async def model_endpoint(
            self, request: Request, repository: RepositoryProtocol[MyModel]
        ) -> Response:
            return await self.render_template(request, "custom.html.jinja")

    class ModelViewItemCustom(ModelView[MyModel]):
        async def model_endpoint(
            self, request: Request, repository: RepositoryProtocol[MyModel]
        ) -> Response:
            item = await self.get_by_pk_or_404(repository, request.path_params["pk"])
            return await self.render_template(
                request, "item_custom.html.jinja", {"item": item}
            )

    return AdminViewGroup(
        renderer=Renderer.create_with_loaders(
            [PackageLoader("tests.app", "templates")]
        ),
        index_view="index",
        children=[
            AdminViewIndex("/"),
            ModelViewGroup[MyModel](
                "/my-model",
                "my_model",
                title="My Model",
                get_repository=functools.partial(get_my_model_repository, items),
                index_view="list",
                children=[
                    ModelViewList[MyModel](
                        path="/",
                        name="list",
                        title="List",
                        fields=(
                            ("id", "ID"),
                            ("label", "Label"),
                            ("created_at", "Created At"),
                        ),
                        query_fields=("id", "label"),
                        details_view_name="edit",
                    ),
                    ModelViewCustom(
                        path="/custom",
                        name="custom",
                        title="My Custom View",
                    ),
                    ModelViewEdit[MyModel](
                        path="/{pk}",
                        name="edit",
                        title="Edit",
                        fields=(
                            (
                                "label",
                                StringField(
                                    "Label",
                                    description="The label of the item",
                                    validators=[
                                        validators.InputRequired(),
                                        validators.Length(min=3),
                                    ],
                                ),
                            ),
                        ),
                    ),
                    ModelViewItemCustom(
                        path="/{pk}/custom-item",
                        name="custom_item",
                        title="My Custom Item View",
                        navigation=False,
                        item_view=True,
                    ),
                ],
            ),
        ],
    )


app = Starlette()
admin = create_admin(
    {
        f"item_{i}": MyModel(
            id=f"item_{i}",
            label=f"Item {i}",
            created_at=datetime.datetime.now(),
        )
        for i in range(10)
    }
)
app.mount("/admin", admin.route)

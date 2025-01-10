import contextlib
import urllib
import urllib.parse
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Sequence,
)
from typing import (
    Any,
    ClassVar,
    Generic,
    Protocol,
    TypedDict,
    TypeVar,
    Union,
)

import wtforms
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, Router

from ._constants import ROUTE_NAME_PREFIX
from ._normalization import class_name_to_url_path
from ._routing import get_current_route
from .exceptions import ASGIAdminConfigurationError, ASGIAdminNotFound
from .repository import Model, RepositoryProtocol, Sorting, SortingOrder
from .templating import templates

ViewType = TypeVar("ViewType", bound="ViewBase")
RouteType = Callable[[ViewType, Request], Awaitable[Response]]


def route(
    path: str,
    methods: list[str],
    *,
    name: Union[str, None] = None,
    index: bool = False,
) -> Callable[[RouteType], RouteType]:
    def decorator(func: RouteType) -> RouteType:
        func._route_info = {  # type: ignore
            "path": path,
            "methods": methods,
            "name": name,
            "index": index,
        }
        return func

    return decorator


class ViewConfigurationError(ASGIAdminConfigurationError):
    """
    Raised when a view is not correctly configured.

    Parameters:
        message: The error message.
        cls: The view class.
    """

    def __init__(
        self,
        message: str,
        cls: type["ViewBase"],
    ) -> None:
        self.cls = cls
        super().__init__(message)


class MissingViewTitleError(ViewConfigurationError):
    """
    Raised when a view is missing a title.

    Parameters:
        cls: The view class.
    """

    def __init__(self, cls: type["ViewBase"]) -> None:
        super().__init__(
            f"The `title` attribute must be set on the view class {cls.__name__}", cls
        )


class MissingViewPrefixError(ViewConfigurationError):
    """
    Raised when a view is missing a prefix.

    Parameters:
        cls: The view class.
    """

    def __init__(self, cls: type["ViewBase"]) -> None:
        super().__init__(
            f"The `prefix` attribute must be set on the view class {cls.__name__}", cls
        )


class ViewBase:
    title: ClassVar[str]
    prefix: ClassVar[str]
    router: Router
    index_route: Route

    _endpoint_route_name_map: dict[Callable[..., Any], str]

    def __init_subclass__(cls, **kwargs) -> None:
        if cls.__name__ != "ModelView":
            if not hasattr(cls, "title"):
                raise MissingViewTitleError(cls)
            if not hasattr(cls, "prefix"):
                raise MissingViewPrefixError(cls)
        super().__init_subclass__(**kwargs)

    def __init__(self) -> None:
        routes: list[Route] = []
        _endpoint_route_name_map: dict[RouteType, str] = {}
        for attr_name in dir(self):
            attr_value = getattr(self, attr_name)
            if hasattr(attr_value, "_route_info"):
                route_info = attr_value._route_info
                name = (
                    route_info["name"]
                    or f"{ROUTE_NAME_PREFIX}{self.__class__.__name__}.{attr_name}"
                )
                route = Route(
                    route_info["path"],
                    attr_value,
                    methods=route_info["methods"],
                    name=name,
                )
                routes.append(route)
                _endpoint_route_name_map[attr_value] = name
                if route_info["index"]:
                    index_route = route

        if index_route is None:
            index_route = routes[0]

        self.router = Router(routes=routes)
        self.index_route = index_route
        self._endpoint_route_name_map = _endpoint_route_name_map

    def get_route_name(self, handler: Callable[..., Any]) -> str:
        return self._endpoint_route_name_map[handler]


class MissingModelViewModelError(ViewConfigurationError):
    """
    Raised when a model view is missing a model.

    Parameters:
        cls: The model view class.
    """

    def __init__(self, cls: type["ModelView"]) -> None:
        super().__init__(
            f"The `model` attribute must be set on the model view class {cls.__name__}",
            cls,
        )


class MissingModelViewModelIdGetterError(ViewConfigurationError):
    """
    Raised when a model view is missing a model id getter.

    Parameters:
        cls: The model view class.
    """

    def __init__(self, cls: type["ModelView"]) -> None:
        super().__init__(
            f"The `model_id_getter` attribute must be set on the model view class {cls.__name__}",
            cls,
        )


class MissingModelViewListFieldsError(ViewConfigurationError):
    """
    Raised when a model view is missing a list of fields.

    Parameters:
        cls: The model view class.
    """

    def __init__(self, cls: type["ModelView"]) -> None:
        super().__init__(
            f"The `list_fields` attribute must be set on the model view class {cls.__name__}",
            cls,
        )


def _build_form_class(
    fields: Sequence[tuple[str, wtforms.Field]],
) -> type[wtforms.Form]:
    class Form(wtforms.Form):
        pass

    for field_name, field in fields:
        setattr(Form, field_name, field)
    return Form


class PaginationOutput(TypedDict):
    offset: int
    limit: int
    total: int
    range: tuple[int, int]
    next_route: Union[str, None]
    previous_route: Union[str, None]


class SortingOutput(TypedDict):
    fields: dict[str, Union[SortingOrder, None]]
    get_sorting_route: Callable[[str], str]


class BreadcrumbItem(TypedDict):
    label: str
    url: Union[str, URL]
    active: bool


class ModelIDGetterProtocol(Protocol[Model]):  # type: ignore
    def __call__(self, item: Model, /) -> Any: ...


class ModelView(ViewBase, Generic[Model]):
    model: ClassVar[type[Any]]
    model_id_getter: ClassVar[ModelIDGetterProtocol[Any]]
    field_labels: ClassVar[dict[str, str]] = {}

    list_default_limit: ClassVar[int] = 10
    list_fields: ClassVar[Sequence[str]]
    list_sortable_fields: ClassVar[Iterable[str]]
    list_query_fields: ClassVar[Iterable[str]] = ()

    edit_fields: ClassVar[Sequence[tuple[str, wtforms.Field]]] = ()
    edit_form_class: ClassVar[type[wtforms.Form]]

    def __init_subclass__(cls, **kwargs):
        if not hasattr(cls, "model"):
            raise MissingModelViewModelError(cls)
        if not hasattr(cls, "model_id_getter"):
            raise MissingModelViewModelIdGetterError(cls)
        if not hasattr(cls, "list_fields"):
            raise MissingModelViewListFieldsError(cls)
        if not hasattr(cls, "title"):
            cls.title = cls.model.__name__
        if not hasattr(cls, "prefix"):
            cls.prefix = f"/{class_name_to_url_path(cls.model.__name__)}"
        if not hasattr(cls, "list_sortable_fields"):
            cls.list_sortable_fields = cls.list_fields
        if not hasattr(cls, "edit_form_class"):
            cls.edit_form_class = _build_form_class(cls.edit_fields)
        super().__init_subclass__(**kwargs)

    def __init__(self) -> None:
        super().__init__()
        self._get_repository_context = contextlib.asynccontextmanager(
            self.get_repository
        )

    async def get_repository(
        self, request: Request
    ) -> AsyncIterator[RepositoryProtocol[Model]]:  # pragma: no cover
        raise NotImplementedError()
        # Trick to make mypy happy about this method being an async iterator
        # Ref: https://mypy.readthedocs.io/en/stable/more_types.html#asynchronous-iterators
        if False:
            yield

    async def get_item_title(self, request: Request, item: Model) -> str:
        return str(item)

    @route("/", methods=["GET"], index=True)
    async def list(self, request: Request) -> Response:
        offset, limit = self._get_pagination_input(request)
        sorting = self._get_sorting_input(request)
        query = await self._get_query_input(request)

        async with self._get_repository_context(request) as repository:
            total, items = await repository.list(
                sorting, offset, limit, query=query, query_fields=self.list_query_fields
            )

        breadcrumbs: list[BreadcrumbItem] = [
            {
                "label": self.title,
                "url": request.url_for(self.get_route_name(self.list)),
                "active": True,
            },
        ]
        return templates.TemplateResponse(
            request,
            "views/model/list.html.jinja",
            {
                "page_title": self.title,
                "breadcrumbs": breadcrumbs,
                "view": self,
                "items": items,
                "pagination": self._get_pagination_output(
                    request, offset, limit, total
                ),
                "sorting": self._get_sorting_output(request, sorting),
                "query": query,
            },
        )

    @route("/{id}", methods=["GET", "POST"])
    async def edit(self, request: Request) -> Response:
        async with self._get_repository_context(request) as repository:
            item = await repository.get_by_id(request.path_params["id"])
            if item is None:
                raise ASGIAdminNotFound()

            form_data = await request.form()
            form = self.edit_form_class(form_data, obj=item)

            status_code = 200
            if request.method == "POST":
                if form.validate():
                    item = await repository.update(item, form.data)
                    # TODO: Success message
                else:
                    status_code = 400

        breadcrumbs: list[BreadcrumbItem] = [
            {
                "label": self.title,
                "url": request.url_for(self.get_route_name(self.list)),
                "active": False,
            },
            {
                "label": await self.get_item_title(request, item),
                "url": request.url_for(
                    self.get_route_name(self.edit), id=self.model_id_getter(item)
                ),
                "active": True,
            },
        ]
        return templates.TemplateResponse(
            request,
            "views/model/edit.html.jinja",
            {
                "page_title": await self.get_item_title(request, item),
                "breadcrumbs": breadcrumbs,
                "view": self,
                "item": item,
                "form": form,
            },
            status_code=status_code,
        )

    def _get_pagination_input(self, request: Request) -> tuple[int, int]:
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", self.list_default_limit))
        return offset, limit

    def _get_pagination_output(
        self, request: Request, offset: int, limit: int, total: int
    ) -> PaginationOutput:
        current_route = get_current_route(request)
        assert current_route is not None

        next_offset = offset + limit
        next_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": next_offset}
        )
        next_route = (
            f"{request.url_for(current_route)}?{next_query_params}"
            if next_offset < total
            else None
        )

        previous_offset = offset - limit
        previous_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": previous_offset}
        )
        previous_route = (
            f"{request.url_for(current_route)}?{previous_query_params}"
            if previous_offset >= 0
            else None
        )

        return {
            "offset": offset,
            "limit": limit,
            "total": total,
            "range": (offset, min(offset + limit, total)),
            "next_route": next_route,
            "previous_route": previous_route,
        }

    def _get_sorting_input(self, request: Request) -> Sorting:
        sorting_param = request.query_params.get("sorting")
        if sorting_param is None:
            return []

        sorting = []
        for field in sorting_param.split(","):
            order = SortingOrder.ASC
            if field.startswith("-"):
                order = SortingOrder.DESC
                field = field[1:]
            if field in self.list_sortable_fields:
                sorting.append((field, order))
        return sorting

    def _get_sorting_output(self, request: Request, sorting: Sorting) -> SortingOutput:
        current_route = get_current_route(request)
        assert current_route is not None

        fields: dict[str, Union[SortingOrder, None]] = {
            field: None for field in self.list_sortable_fields
        }
        for field, current_order in sorting:
            fields[field] = current_order

        def get_sorting_route(field: str) -> str:
            sorting_param = []
            field_found = False
            for current_field, current_order in sorting:
                if current_field != field:
                    sorting_param.append(
                        f"{current_field}"
                        if current_order == SortingOrder.ASC
                        else f"-{current_field}"
                    )
                else:
                    field_found = True
                    if current_order == SortingOrder.DESC:
                        continue
                    else:
                        sorting_param.append(f"-{field}")

            if not field_found:
                sorting_param.append(field)

            query_params = urllib.parse.urlencode(
                {**request.query_params, "sorting": ",".join(sorting_param)}
            )
            return f"{request.url_for(current_route)}?{query_params}"

        return {"fields": fields, "get_sorting_route": get_sorting_route}

    async def _get_query_input(self, request: Request) -> Union[str, None]:
        query = request.query_params.get("query")
        if query is not None:
            return query.strip()
        return None

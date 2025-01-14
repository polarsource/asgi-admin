import functools
import urllib.parse
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Callable, Generic, TypedDict, Union

import wtforms
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, request_response
from starlette.types import Receive, Scope, Send

from asgi_admin._constants import ROUTE_NAME_SEPARATOR

from ._breadcrumbs import BreadcrumbItem
from .exceptions import ASGIAdminConfigurationError, ASGIAdminNotFound
from .repository import Model, Sorting, SortingOrder
from .templating import Renderer, default_renderer

if TYPE_CHECKING:
    from .viewsets import ModelViewSet, ViewSet


class ViewConfigurationError(TypeError, ASGIAdminConfigurationError):
    """
    Raised when a view is not correctly configured.

    Parameters:
        message: The error message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        super(ASGIAdminConfigurationError, self).__init__(message)


class ViewBase:
    path: str
    methods: Iterable[str]
    name: str
    title: str
    _viewset: Union["ViewSet", None] = None

    def __init__(
        self,
        path: str,
        name: str,
        methods: Iterable[str] = ["GET"],
        *,
        title: Union[str, None] = None,
    ):
        self.path = path
        self.name = name
        self.methods = methods or self.methods
        self.title = title or self.name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return await request_response(self.handle)(scope, receive, send)

    async def handle(self, request: Request) -> Response:
        raise NotImplementedError()  # pragma: no cover

    @functools.cached_property
    def route_name(self) -> str:
        if self.viewset is None:
            return self.name
        return f"{self.viewset.route_name}{ROUTE_NAME_SEPARATOR}{self.name}"

    @functools.cached_property
    def route(self) -> Route:
        return Route(self.path, self, methods=list(self.methods), name=self.route_name)

    @property
    def viewset(self) -> Union["ViewSet", None]:
        return self._viewset

    @viewset.setter
    def viewset(self, viewset: "ViewSet") -> None:
        self._viewset = viewset

    @property
    def renderer(self) -> Renderer:
        if self.viewset is None:
            return default_renderer
        return self.viewset.renderer

    async def get_title(self, request: Request) -> str:
        return self.title

    def is_nested(self, viewset: "ViewSet") -> bool:
        if self.viewset is None:
            return False
        if self.viewset == viewset:
            return True
        return self.viewset.is_nested(viewset)

    async def get_breadcrumbs(self, request: Request) -> list[BreadcrumbItem]:
        breadcrumbs: list[BreadcrumbItem] = []
        if self.viewset is not None:
            breadcrumbs.extend(self.viewset.get_breadcrumbs(request))

        title = await self.get_title(request)
        breadcrumbs.append({"label": title, "url": request.url, "active": True})
        return breadcrumbs

    def render_template(
        self,
        request: Request,
        name: str,
        context: Union[dict[str, Any], None] = None,
        status_code: int = 200,
        headers: Union[Mapping[str, str], None] = None,
        media_type: Union[str, None] = None,
        background: Union[BackgroundTask, None] = None,
    ) -> Response:
        return self.renderer.TemplateResponse(
            request,
            name,
            context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


class NotTiedToModelViewSetError(ViewConfigurationError):
    """
    Raised when a model view is not tied to a ModelViewSet.
    """

    def __init__(self) -> None:
        super().__init__("View is not tied to a ModelViewSet.")


class ModelView(Generic[Model], ViewBase):
    _viewset: "Union[ModelViewSet[Model], None]" = None

    @property
    def viewset(self) -> "ModelViewSet[Model]":
        if self._viewset is None:
            raise NotTiedToModelViewSetError()
        return self._viewset

    @viewset.setter
    def viewset(self, viewset: "ModelViewSet[Model]") -> None:
        self._viewset = viewset


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


class ModelViewList(ModelView[Model]):
    default_limit: int
    fields: dict[str, str]
    sortable_fields: Iterable[str]
    query_fields: Iterable[str]

    def __init__(
        self,
        *,
        title: str,
        default_limit: int = 10,
        fields: Sequence[Union[str, tuple[str, str]]],
        sortable_fields: Union[Iterable[str], None] = None,
        query_fields: Union[Iterable[str], None] = None,
        path: str,
        name: str,
    ) -> None:
        self.default_limit = default_limit

        self.fields: dict[str, str] = {}
        for field in fields:
            if isinstance(field, str):
                self.fields[field] = field
            else:
                self.fields[field[0]] = field[1]

        self.sortable_fields = sortable_fields or list(self.fields.keys())
        self.query_fields = query_fields or ()
        super().__init__(path=path, name=name, methods=["GET"], title=title)

    async def handle(self, request: Request) -> Response:
        offset, limit = self._get_pagination_input(request)
        sorting = self._get_sorting_input(request)
        query = await self._get_query_input(request)

        async with self.viewset.get_repository(request) as repository:
            total, items = await repository.list(
                sorting, offset, limit, query=query, query_fields=self.query_fields
            )

        return self.render_template(
            request,
            "views/model/list.html.jinja",
            {
                "page_title": await self.get_title(request),
                "breadcrumbs": await self.get_breadcrumbs(request),
                "view": self,
                "items": items,
                "pagination": self._get_pagination_output(
                    request, offset, limit, total
                ),
                "sorting": self._get_sorting_output(request, sorting),
                "query": query,
            },
        )

    def _get_pagination_input(self, request: Request) -> tuple[int, int]:
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", self.default_limit))
        return offset, limit

    def _get_pagination_output(
        self, request: Request, offset: int, limit: int, total: int
    ) -> PaginationOutput:
        next_offset = offset + limit
        next_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": next_offset}
        )
        next_route = (
            f"{request.url_for(self.route_name)}?{next_query_params}"
            if next_offset < total
            else None
        )

        previous_offset = offset - limit
        previous_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": previous_offset}
        )
        previous_route = (
            f"{request.url_for(self.route_name)}?{previous_query_params}"
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
            if field in self.sortable_fields:
                sorting.append((field, order))
        return sorting

    def _get_sorting_output(self, request: Request, sorting: Sorting) -> SortingOutput:
        fields: dict[str, Union[SortingOrder, None]] = {
            field: None for field in self.sortable_fields
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
            return f"{request.url_for(self.route_name)}?{query_params}"

        return {"fields": fields, "get_sorting_route": get_sorting_route}

    async def _get_query_input(self, request: Request) -> Union[str, None]:
        query = request.query_params.get("query")
        if query is not None:
            return query.strip()
        return None


def _build_form_class(
    fields: Sequence[tuple[str, wtforms.Field]],
) -> type[wtforms.Form]:
    class Form(wtforms.Form):
        pass

    for field_name, field in fields:
        setattr(Form, field_name, field)
    return Form


class ModelViewEditFieldsConfigurationError(ViewConfigurationError):
    """
    Raised when both `edit_fields` and `edit_form_class` are not provided.
    """

    def __init__(self) -> None:
        super().__init__("Either `edit_fields` or `edit_form_class` must be provided.")


class ModelViewEdit(ModelView[Model]):
    edit_fields: Sequence[tuple[str, wtforms.Field]]
    edit_form_class: type[wtforms.Form]

    def __init__(
        self,
        *,
        edit_fields: Union[Sequence[tuple[str, wtforms.Field]], None] = None,
        edit_form_class: Union[type[wtforms.Form], None] = None,
        path: str,
        name: str,
    ) -> None:
        if edit_form_class is not None:
            self.edit_form_class = edit_form_class
        elif edit_fields is not None:
            self.edit_form_class = _build_form_class(edit_fields)
        else:
            raise ModelViewEditFieldsConfigurationError()
        super().__init__(path=path, name=name, methods=["GET", "POST"])

    async def handle(self, request: Request) -> Response:
        async with self.viewset.get_repository(request) as repository:
            item = await repository.get_by_id(request.path_params["pk"])
            if item is None:
                raise ASGIAdminNotFound()
            request.state.item = item

            form_data = await request.form()
            form = self.edit_form_class(form_data, obj=item)

            status_code = 200
            if request.method == "POST":
                if form.validate():
                    item = await repository.update(item, form.data)
                    # TODO: Success message
                else:
                    status_code = 400

        return self.render_template(
            request,
            "views/model/edit.html.jinja",
            {
                "page_title": await self.get_title(request),
                "breadcrumbs": await self.get_breadcrumbs(request),
                "view": self,
                "item": item,
                "form": form,
            },
            status_code=status_code,
        )

    async def get_title(self, request: Request) -> str:
        item: Model = request.state.item
        return self.viewset.item_title_getter(item)


class AdminIndexView(ViewBase):
    def __init__(
        self,
        path: str,
        name: str,
        *,
        title: Union[str, None] = "Dashboard",
    ) -> None:
        super().__init__(path, name, ["GET"], title=title)

    async def handle(self, request: Request) -> Response:
        return self.render_template(
            request,
            "views/admin/index.html.jinja",
            {
                "page_title": await self.get_title(request),
                "breadcrumbs": await self.get_breadcrumbs(request),
                "view": self,
            },
        )

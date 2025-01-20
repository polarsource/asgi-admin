import contextlib
import functools
import inspect
import urllib.parse
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Callable, Generic, TypedDict, Union

import wtforms
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Mount, Route, request_response
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_admin._constants import ROUTE_NAME_SEPARATOR, SCOPE_ROOT_VIEW

from ._breadcrumbs import BreadcrumbItem
from .exceptions import ASGIAdminConfigurationError, ASGIAdminNotFound
from .repository import Model, RepositoryProtocol, Sorting, SortingOrder
from .templating import Renderer, default_renderer

if TYPE_CHECKING:
    pass


class ViewConfigurationError(TypeError, ASGIAdminConfigurationError):
    """
    Raised when a view is not correctly configured.

    Parameters:
        message: The error message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        super(ASGIAdminConfigurationError, self).__init__(message)


class NoRendererSetError(ViewConfigurationError):
    """
    Raised when no renderer is set on a view or its ancestors.

    Parameters:
        view: The view that does not have a renderer set.
    """

    def __init__(self, view: "ViewBase") -> None:
        self.view = view
        super().__init__(
            f"No template renderer is set on view {view.name}. "
            "A view or one of its ancestors must have a renderer set to render a template."
        )


class ViewBase:
    path: str
    name: str
    title: str
    navigation: bool
    children: list["ViewBase"]
    middleware: list[Middleware]
    _parent: Union["ViewBase", None] = None
    _renderer: Union[Renderer, None] = None

    def __init__(
        self,
        path: str,
        name: str,
        *,
        title: Union[str, None] = None,
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        children: Union[Sequence["ViewBase"], None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        self.path = path
        self.name = name
        self.title = title or name
        self.navigation = navigation
        self._parent = parent
        self.children = []
        for child in children or []:
            self.add_child(child)
        self._renderer = renderer
        self.middleware = [] if middleware is None else list(middleware)

    @functools.cached_property
    def route(self) -> BaseRoute:
        raise NotImplementedError()  # pragma: no cover

    @functools.cached_property
    def route_name(self) -> str:
        if self.parent is None:
            return self.name
        return f"{self.parent.route_name}{ROUTE_NAME_SEPARATOR}{self.name}"

    @property
    def parent(self) -> Union["ViewBase", None]:
        return self._parent

    @parent.setter
    def parent(self, parent: "ViewBase") -> None:
        self._parent = parent

    @property
    def renderer(self) -> Renderer:
        if self._renderer is not None:
            return self._renderer
        if self.parent is not None:
            return self.parent.renderer
        raise NoRendererSetError(self)

    def add_child(self, child: "ViewBase") -> None:
        child.parent = self
        self.children.append(child)

    def get_view(self, name: str) -> Union["ViewBase", None]:
        for child in self.children:
            if child.name == name:
                return child
        return None

    def is_nested(self, view: "ViewBase") -> bool:
        if self.parent is None:
            return False
        if self == view:
            return True
        return self.parent.is_nested(view)

    async def get_title(self, request: Request) -> str:
        return self.title

    async def get_breadcrumbs(
        self, request: Request, *, current: Union["ViewBase", None] = None
    ) -> list[BreadcrumbItem]:
        current = current or self

        breadcrumbs: list[BreadcrumbItem] = []
        if self.parent is not None:
            parent_breadcrumbs = await self.parent.get_breadcrumbs(
                request, current=current
            )
            breadcrumbs.extend(parent_breadcrumbs)

        title = await self.get_title(request)
        if self == current:
            breadcrumbs.append({"label": title, "url": request.url})
        elif isinstance(self, View):
            breadcrumbs.append(
                {"label": title, "url": request.url_for(self.route_name)}
            )
        elif isinstance(self, ViewGroup) and (index_view := self.get_index_view()):
            breadcrumbs.append(
                {"label": title, "url": request.url_for(index_view.route_name)}
            )

        return breadcrumbs


class ViewGroup(ViewBase):
    index_view: Union[str, None] = None

    def __init__(
        self,
        path: str,
        name: str,
        *,
        title: Union[str, None] = None,
        navigation: bool = True,
        index_view: Union[str, None] = None,
        parent: Union["ViewBase", None] = None,
        children: Union[Sequence["ViewBase"], None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        super().__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            parent=parent,
            children=children,
            renderer=renderer,
            middleware=middleware,
        )
        self.index_view = index_view

    @functools.cached_property
    def route(self) -> BaseRoute:
        return Mount(
            self.path,
            routes=[child.route for child in self.children],
            middleware=self.middleware,
        )

    def get_index_view(self) -> Union["ViewBase", None]:
        if self.index_view is not None:
            return self.get_view(self.index_view)
        return None


class View(ViewBase):
    methods: Iterable[str]

    def __init__(
        self,
        path: str,
        name: str,
        methods: Iterable[str] = ["GET"],
        *,
        title: Union[str, None] = None,
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
    ):
        super().__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            parent=parent,
            children=[],
            renderer=renderer,
            middleware=middleware,
        )
        self.methods = methods or self.methods

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return await request_response(self.endpoint)(scope, receive, send)

    async def endpoint(self, request: Request) -> Response:
        raise NotImplementedError()  # pragma: no cover

    @functools.cached_property
    def route(self) -> BaseRoute:
        return Route(
            self.path,
            self,
            methods=list(self.methods),
            name=self.route_name,
            middleware=self.middleware,
        )

    async def get_base_context(self, request: Request) -> dict[str, Any]:
        return {
            "page_title": await self.get_title(request),
            "breadcrumbs": await self.get_breadcrumbs(request),
            "view": self,
        }

    async def render_template(
        self,
        request: Request,
        name: str,
        context: Union[dict[str, Any], None] = None,
        status_code: int = 200,
        headers: Union[Mapping[str, str], None] = None,
        media_type: Union[str, None] = None,
        background: Union[BackgroundTask, None] = None,
    ) -> Response:
        context = {
            **(await self.get_base_context(request)),
            **(context or {}),
        }
        return self.renderer.TemplateResponse(
            request,
            name,
            context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


class NoRepositoryGetterSetError(ViewConfigurationError):
    """
    Raised when no repository getter is set on a model view or its ancestors.

    Parameters:
        view: The model view that does not have a repository getter set.
    """

    def __init__(self, view: "ModelViewBase") -> None:
        self.view = view
        super().__init__(
            f'No repository getter is set on model view "{view.name}". '
            "A model view or one of its ancestors must have a repository getter set."
        )


class ModelViewBase(ViewBase, Generic[Model]):
    _get_repository: Union[
        Callable[
            [Request], contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]]
        ],
        None,
    ] = None

    def __init__(
        self,
        path: str,
        name: str,
        *,
        title: Union[str, None] = None,
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        children: Union[Sequence["ViewBase"], None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
            None,
        ] = None,
    ) -> None:
        super().__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            parent=parent,
            children=children,
            renderer=renderer,
            middleware=middleware,
        )
        if inspect.isasyncgenfunction(get_repository):
            self._get_repository = contextlib.asynccontextmanager(get_repository)
        else:
            self._get_repository = get_repository  # type: ignore

    @property
    def get_repository(
        self,
    ) -> Callable[
        [Request], contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]]
    ]:
        if self._get_repository is not None:
            return self._get_repository
        if self.parent is not None and isinstance(self.parent, ModelViewBase):
            return self.parent.get_repository
        raise NoRepositoryGetterSetError(self)

    async def get_by_pk_or_404(
        self, repository: RepositoryProtocol[Model], pk: Any
    ) -> Model:
        item = await repository.get_by_pk(pk)
        if item is None:
            raise ASGIAdminNotFound()
        return item


class ModelViewGroup(ViewGroup, ModelViewBase[Model]):
    def __init__(
        self,
        path: str,
        name: str,
        *,
        title: Union[str, None] = None,
        navigation: bool = True,
        index_view: Union[str, None] = None,
        parent: Union["ViewBase", None] = None,
        children: Union[Sequence["ViewBase"], None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
            None,
        ] = None,
    ):
        super().__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            index_view=index_view,
            parent=parent,
            children=children,
            middleware=middleware,
            renderer=renderer,
        )
        super(ViewGroup, self).__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            parent=parent,
            children=children,
            renderer=renderer,
            middleware=middleware,
            get_repository=get_repository,
        )


class ModelView(View, ModelViewBase[Model]):
    item_view: bool

    def __init__(
        self,
        path: str,
        name: str,
        methods: Iterable[str] = ["GET"],
        *,
        item_view: bool = False,
        title: Union[str, None] = None,
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
            None,
        ] = None,
    ):
        super().__init__(
            path,
            name,
            methods,
            title=title,
            navigation=navigation,
            parent=parent,
            middleware=middleware,
            renderer=renderer,
        )
        super(View, self).__init__(
            path,
            name,
            title=title,
            navigation=navigation,
            parent=parent,
            children=[],
            renderer=renderer,
            middleware=middleware,
            get_repository=get_repository,
        )
        self.item_view = item_view

    async def endpoint(self, request: Request) -> Response:
        async with self.get_repository(request) as repository:
            request.state.repository = repository
            return await self.model_endpoint(request, repository)

    async def model_endpoint(
        self, request: Request, repository: RepositoryProtocol[Model]
    ) -> Response:
        raise NotImplementedError()  # pragma: no cover

    async def get_base_context(self, request: Request) -> dict[str, Any]:
        return {
            **await super().get_base_context(request),
            "repository": request.state.repository,
        }


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
    details_view_name: Union[str, None]

    def __init__(
        self,
        path: str,
        name: str,
        *,
        default_limit: int = 10,
        fields: Sequence[Union[str, tuple[str, str]]],
        sortable_fields: Union[Iterable[str], None] = None,
        query_fields: Union[Iterable[str], None] = None,
        details_view_name: Union[str, None] = None,
        title: Union[str, None] = None,
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
            None,
        ] = None,
    ):
        super().__init__(
            path,
            name,
            ["GET"],
            title=title,
            navigation=navigation,
            parent=parent,
            renderer=renderer,
            middleware=middleware,
            get_repository=get_repository,
        )
        self.default_limit = default_limit

        self.fields: dict[str, str] = {}
        for field in fields:
            if isinstance(field, str):
                self.fields[field] = field
            else:
                self.fields[field[0]] = field[1]

        self.sortable_fields = sortable_fields or list(self.fields.keys())
        self.query_fields = query_fields or ()
        self.details_view_name = details_view_name

    async def model_endpoint(
        self, request: Request, repository: RepositoryProtocol[Model]
    ) -> Response:
        offset, limit = self._get_pagination_input(request)
        sorting = self._get_sorting_input(request)
        query = await self._get_query_input(request)

        total, items = await repository.list(
            sorting, offset, limit, query=query, query_fields=self.query_fields
        )

        return await self.render_template(
            request,
            "views/model/list.html.jinja",
            {
                "items": items,
                "pagination": self._get_pagination_output(
                    request, offset, limit, total
                ),
                "sorting": self._get_sorting_output(request, sorting),
                "query": query,
                "details_view": self._get_details_view(),
                "item_views": self._get_item_views(),
            },
        )

    def _get_details_view(self) -> Union[ViewBase, None]:
        if self.parent is None or self.details_view_name is None:
            return None
        return self.parent.get_view(self.details_view_name)

    def _get_item_views(self) -> list[ViewBase]:
        if self.parent is None:
            return []

        return [
            sibling
            for sibling in self.parent.children
            if isinstance(sibling, ModelView) and sibling.item_view
        ]

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
    Raised when both `fields` and `form_class` are not provided.
    """

    def __init__(self) -> None:
        super().__init__("Either `fields` or `form_class` must be provided.")


class ModelViewEdit(ModelView[Model]):
    fields: Sequence[tuple[str, wtforms.Field]]
    form_class: type[wtforms.Form]

    def __init__(
        self,
        path: str,
        name: str,
        *,
        fields: Union[Sequence[tuple[str, wtforms.Field]], None] = None,
        form_class: Union[type[wtforms.Form], None] = None,
        title: Union[str, None] = None,
        parent: Union["ViewBase", None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
            None,
        ] = None,
    ) -> None:
        super().__init__(
            path,
            name,
            ["GET", "POST"],
            title=title,
            navigation=False,
            parent=parent,
            renderer=renderer,
            middleware=middleware,
            get_repository=get_repository,
        )

        if form_class is not None:
            self.form_class = form_class
        elif fields is not None:
            self.form_class = _build_form_class(fields)
        else:
            raise ModelViewEditFieldsConfigurationError()

    async def model_endpoint(
        self, request: Request, repository: RepositoryProtocol[Model]
    ) -> Response:
        item = await self.get_by_pk_or_404(repository, request.path_params["pk"])
        request.state.item = item

        form_data = await request.form()
        form = self.form_class(form_data, obj=item)

        status_code = 200
        if request.method == "POST":
            if form.validate():
                item = await repository.update(item, form.data)
                # TODO: Success message
            else:
                status_code = 400

        return await self.render_template(
            request,
            "views/model/edit.html.jinja",
            {"item": item, "form": form},
            status_code=status_code,
        )

    async def get_title(self, request: Request) -> str:
        item: Model = request.state.item
        return request.state.repository.get_title(item)


class AdminViewMiddleware:
    def __init__(self, app: ASGIApp, view: "AdminViewGroup") -> None:
        self.app = app
        self.view = view

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            scope["state"][SCOPE_ROOT_VIEW] = self.view
        await self.app(scope, receive, send)


class AdminViewGroup(ViewGroup):
    def __init__(
        self,
        name: str = "asgi_admin",
        *,
        title: Union[str, None] = "ASGI Admin",
        index_view: Union[str, None] = None,
        parent: Union["ViewBase", None] = None,
        children: Union[Sequence["ViewBase"], None] = None,
        renderer: Union[Renderer, None] = default_renderer,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        super().__init__(
            "/",
            name,
            title=title,
            navigation=True,
            index_view=index_view,
            parent=parent,
            children=children,
            renderer=renderer,
            middleware=[
                Middleware(AdminViewMiddleware, view=self),
                *(middleware or []),
            ],
        )


class AdminViewIndex(View):
    def __init__(
        self,
        name: str = "index",
        *,
        title: Union[str, None] = "Dashboard",
        navigation: bool = True,
        parent: Union["ViewBase", None] = None,
        renderer: Union[Renderer, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
    ):
        super().__init__(
            "/",
            name,
            ["GET"],
            title=title,
            navigation=navigation,
            parent=parent,
            middleware=middleware,
            renderer=renderer,
        )

    async def endpoint(self, request: Request) -> Response:
        return await self.render_template(request, "views/admin/index.html.jinja")

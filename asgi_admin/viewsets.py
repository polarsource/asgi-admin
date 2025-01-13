import contextlib
import functools
import inspect
from collections.abc import (
    AsyncIterator,
    Callable,
    Iterable,
    Sequence,
)
from typing import Any, Generic, Union

import wtforms
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.routing import BaseRoute, Mount, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_admin._constants import ROUTE_NAME_SEPARATOR, SCOPE_NAVIGATION_KEY

from ._breadcrumbs import BreadcrumbItem
from .repository import Model, RepositoryProtocol
from .views import AdminIndexView, ModelViewEdit, ModelViewList, ViewBase


class ViewSet:
    name: str
    title: str
    views: list[ViewBase]
    parent_viewset: Union["ViewSet", None] = None
    viewsets: dict[str, "ViewSet"]
    middleware: list[Middleware]

    def __init__(
        self,
        name: str,
        views: Union[Sequence["ViewBase"], None] = None,
        viewsets: Union[dict[str, "ViewSet"], None] = None,
        *,
        title: Union[str, None] = None,
        index_view_name: Union[str, None] = None,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        self.name = name

        self.views = []
        for view in views or []:
            self.add_view(view)

        self.viewsets = {}
        for prefix, viewset in (viewsets or {}).items():
            self.add_viewset(viewset, prefix)

        self.title = title or name
        self.index_view_name = index_view_name

        self.middleware = [] if middleware is None else list(middleware)

    @functools.cached_property
    def route_name(self) -> str:
        if self.parent_viewset is not None:
            return f"{self.parent_viewset.route_name}{ROUTE_NAME_SEPARATOR}{self.name}"
        return self.name

    @functools.cached_property
    def router(self) -> Router:
        routes: list[BaseRoute] = [view.route for view in self.views]
        for prefix, viewset in self.viewsets.items():
            routes.append(Mount(prefix, app=viewset.router))
        return Router(routes=routes, middleware=self.middleware)

    def add_view(self, view: "ViewBase") -> None:
        view.viewset = self
        self.views.append(view)

    def get_view(self, name: str) -> Union["ViewBase", None]:
        for view in self.views:
            if view.name == name:
                return view
        return None

    def get_index_view(self) -> Union["ViewBase", None]:
        if self.index_view_name is None:
            return None
        return self.get_view(self.index_view_name)

    def add_viewset(self, viewset: "ViewSet", prefix: Union[str, None] = None) -> None:
        viewset.parent_viewset = self
        prefix = prefix or f"/{viewset.name}"
        self.viewsets[prefix] = viewset

    def is_nested(self, viewset: "ViewSet") -> bool:
        if self.parent_viewset == viewset:
            return True
        if self.parent_viewset is not None:
            return self.parent_viewset.is_nested(viewset)
        return False

    def get_breadcrumbs(
        self, request: Request, *, breadcrumbs: Union[list[BreadcrumbItem], None] = None
    ) -> list[BreadcrumbItem]:
        breadcrumbs = breadcrumbs or []

        index_view = self.get_index_view()
        if index_view is not None:
            breadcrumbs = [
                {"label": self.title, "url": request.url_for(index_view.route_name)},
                *breadcrumbs,
            ]

        if self.parent_viewset is None:
            return breadcrumbs

        return self.parent_viewset.get_breadcrumbs(request, breadcrumbs=breadcrumbs)


class ModelViewSet(Generic[Model], ViewSet):
    get_repository: Callable[
        [Request], contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]]
    ]
    pk_getter: Callable[[Model], Any]
    item_title_getter: Callable[[Model], str]

    def __init__(
        self,
        name: str,
        *,
        get_repository: Union[
            Callable[[Request], AsyncIterator[RepositoryProtocol[Model]]],
            Callable[
                [Request],
                contextlib.AbstractAsyncContextManager[RepositoryProtocol[Model]],
            ],
        ],
        pk_getter: Callable[[Model], Any],
        item_title_getter: Callable[[Model], str],
        list_fields: Sequence[Union[str, tuple[str, str]]],
        list_sortable_fields: Union[Iterable[str], None] = None,
        list_query_fields: Union[Iterable[str], None] = None,
        edit_fields: Union[Sequence[tuple[str, wtforms.Field]], None] = None,
        edit_form_class: Union[type[wtforms.Form], None] = None,
        views: Union[Sequence[ViewBase], None] = None,
        viewsets: Union[dict[str, "ViewSet"], None] = None,
        title: str,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        if inspect.isasyncgenfunction(get_repository):
            self.get_repository = contextlib.asynccontextmanager(get_repository)
        else:
            self.get_repository = get_repository  # type: ignore

        self.pk_getter = pk_getter
        self.item_title_getter = item_title_getter

        views = [] if views is None else list(views)
        views = [
            ModelViewList(
                fields=list_fields,
                sortable_fields=list_sortable_fields,
                query_fields=list_query_fields,
                title="List",
                path="/",
                name="list",
            ),
            ModelViewEdit(
                edit_fields=edit_fields,
                edit_form_class=edit_form_class,
                path="/{pk}",
                name="edit",
            ),
            *views,
        ]

        super().__init__(
            name,
            views,
            viewsets,
            title=title,
            index_view_name="list",
            middleware=middleware,
        )


class AdminViewSetMiddleware:
    def __init__(self, app: ASGIApp, viewset: "AdminViewSet") -> None:
        self.app = app
        self.viewset = viewset

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            scope["state"][SCOPE_NAVIGATION_KEY] = self.viewset.viewsets.values()
        await self.app(scope, receive, send)


class AdminViewSet(ViewSet):
    def __init__(
        self,
        name: str = "asgi_admin",
        views: Union[Sequence[ViewBase], None] = None,
        viewsets: Union[dict[str, "ViewSet"], None] = None,
        *,
        title: str = "ASGI Admin",
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        views = [] if views is None else list(views)
        views = [
            AdminIndexView(path="/", name="index"),
            *views,
        ]
        middleware = [] if middleware is None else list(middleware)
        middleware = [
            Middleware(AdminViewSetMiddleware, viewset=self),
            *middleware,
        ]
        super().__init__(
            name,
            views,
            viewsets,
            index_view_name="index",
            title=title,
            middleware=middleware,
        )

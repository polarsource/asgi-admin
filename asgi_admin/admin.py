from typing import ClassVar

from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from ._constants import ROUTE_NAME_PREFIX, SCOPE_NAVIGATION_KEY, SCOPE_TITLE_KEY
from .templating import templates
from .views import ViewBase


class AdminStateMiddleware:
    def __init__(self, app: ASGIApp, admin: "AdminBase") -> None:
        self.app = app
        self.admin = admin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            scope["state"][SCOPE_NAVIGATION_KEY] = [
                {
                    "title": view.title,
                    "index_route": view.index_route.name,
                    "view": view,
                }
                for view in self.admin.views
            ]
            scope["state"][SCOPE_TITLE_KEY] = self.admin.title
        await self.app(scope, receive, send)


class AdminBase(Router):
    views: ClassVar[list[ViewBase]] = []
    title: ClassVar[str]
    index_route_name: ClassVar[str] = f"{ROUTE_NAME_PREFIX}.index"

    def __init_subclass__(cls) -> None:
        if not hasattr(cls, "title"):
            cls.title = cls.__name__
        return super().__init_subclass__()

    def __init__(self) -> None:
        routes = [
            Route("/", self.index, methods=["GET"], name=self.index_route_name),
            *(Mount(view.prefix, view.router) for view in self.views),
        ]
        middleware = [
            Middleware(AdminStateMiddleware, admin=self),
        ]
        super().__init__(routes=routes, middleware=middleware)

    async def index(self, request: Request) -> Response:
        return templates.TemplateResponse(request, "index.html.jinja")


__all__ = ["AdminBase"]

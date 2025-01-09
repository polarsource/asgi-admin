from typing import ClassVar

from starlette.middleware import Middleware
from starlette.routing import Mount, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_admin.views import ViewBase


class NavigationMiddleware:
    def __init__(self, app: ASGIApp, views: list[ViewBase]) -> None:
        self.app = app
        self.views = views

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            scope["state"]["_asgi_admin_navigation"] = [
                {
                    "title": view.title,
                    "index_route": view.index_route.name,
                }
                for view in self.views
            ]
        await self.app(scope, receive, send)


class AdminBase(Router):
    views: ClassVar[list[ViewBase]]

    def __init__(self) -> None:
        routes = [Mount(view.prefix, view.router) for view in self.views]
        middleware = [
            Middleware(NavigationMiddleware, views=self.views),
        ]
        super().__init__(routes=routes, middleware=middleware)

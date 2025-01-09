from typing import ClassVar

from starlette.middleware import Middleware
from starlette.routing import Mount, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_admin.views import ViewBase


class AdminStateMiddleware:
    def __init__(self, app: ASGIApp, admin: "AdminBase") -> None:
        self.app = app
        self.admin = admin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            scope["state"]["_asgi_admin_navigation"] = [
                {
                    "title": view.title,
                    "index_route": view.index_route.name,
                }
                for view in self.admin.views
            ]
            scope["state"]["_asgi_admin_title"] = self.admin.title
        await self.app(scope, receive, send)


class AdminBase(Router):
    views: ClassVar[list[ViewBase]] = []
    title: ClassVar[str]

    def __init_subclass__(cls) -> None:
        if not hasattr(cls, "title"):
            cls.title = cls.__name__
        return super().__init_subclass__()

    def __init__(self) -> None:
        routes = [Mount(view.prefix, view.router) for view in self.views]
        middleware = [
            Middleware(AdminStateMiddleware, admin=self),
        ]
        super().__init__(routes=routes, middleware=middleware)


__all__ = ["AdminBase"]
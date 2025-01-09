from collections.abc import Callable
from typing import Any, Union, cast

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from starlette.templating import Jinja2Templates

env = Environment(
    loader=PackageLoader("asgi_admin.templating", "templates"),
    autoescape=select_autoescape(),
)


def navigation_context(request: Request) -> dict[str, Any]:
    return {"navigation": request.state._asgi_admin_navigation}


def _current_route(
    routes: list[Route], endpoint: Callable[..., Any]
) -> Union[str, None]:
    for route in routes:
        if getattr(route, "endpoint", None) == endpoint:
            return route.name
        if sub_route := getattr(route, "routes", None):
            return _current_route(sub_route, endpoint)
    return None


def current_route_context(request: Request) -> dict[str, Union[str, None]]:
    app: Starlette = request.scope["app"]
    endpoint: Callable[..., Any] = request.scope["endpoint"]
    routes: list[Route] = cast(list[Route], app.routes)
    return {"current_route": _current_route(routes, endpoint)}


templates = Jinja2Templates(
    env=env, context_processors=[navigation_context, current_route_context]
)

__all__ = ["templates"]

from collections.abc import Callable
from typing import Any, Union, cast

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route


def _get_current_route(
    routes: list[Route], endpoint: Callable[..., Any]
) -> Union[str, None]:
    for route in routes:
        if getattr(route, "endpoint", None) == endpoint:
            return route.name
        if sub_route := getattr(route, "routes", None):
            return _get_current_route(sub_route, endpoint)
    return None


def get_current_route(request: Request) -> Union[str, None]:
    app: Starlette = request.scope["app"]
    endpoint: Callable[..., Any] = request.scope["endpoint"]
    routes: list[Route] = cast(list[Route], app.routes)
    return _get_current_route(routes, endpoint)


__all__ = ["get_current_route"]

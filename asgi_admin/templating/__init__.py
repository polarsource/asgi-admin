from collections.abc import Callable
from typing import Any, Union

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from .._constants import (
    CONTEXT_CURRENT_ROUTE_KEY,
    CONTEXT_NAVIGATION_KEY,
    CONTEXT_TITLE_KEY,
    SCOPE_NAVIGATION_KEY,
    SCOPE_TITLE_KEY,
)
from .._routing import get_current_route

env = Environment(
    loader=PackageLoader("asgi_admin.templating", "templates"),
    autoescape=select_autoescape(),
)
env.globals = {
    **env.globals,
    CONTEXT_NAVIGATION_KEY: CONTEXT_NAVIGATION_KEY,
    CONTEXT_TITLE_KEY: CONTEXT_TITLE_KEY,
    CONTEXT_CURRENT_ROUTE_KEY: CONTEXT_CURRENT_ROUTE_KEY,
}


def state_context(request: Request) -> dict[str, Any]:
    return {
        CONTEXT_NAVIGATION_KEY: getattr(request.state, SCOPE_NAVIGATION_KEY),
        CONTEXT_TITLE_KEY: getattr(request.state, SCOPE_TITLE_KEY),
    }


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
    return {CONTEXT_CURRENT_ROUTE_KEY: get_current_route(request)}


templates = Jinja2Templates(
    env=env, context_processors=[state_context, current_route_context]
)

__all__ = ["templates"]

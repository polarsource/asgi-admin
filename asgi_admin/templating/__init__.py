from typing import Any, Union

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
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


def state_context(request: Request) -> dict[str, Any]:
    return {
        CONTEXT_NAVIGATION_KEY: getattr(request.state, SCOPE_NAVIGATION_KEY),
        CONTEXT_TITLE_KEY: getattr(request.state, SCOPE_TITLE_KEY),
    }


def current_route_context(request: Request) -> dict[str, Union[str, None]]:
    return {CONTEXT_CURRENT_ROUTE_KEY: get_current_route(request)}


templates = Jinja2Templates(
    env=env, context_processors=[state_context, current_route_context]
)

__all__ = ["templates"]

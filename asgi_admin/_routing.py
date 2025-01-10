from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Union, cast

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.routing import Route

from .exceptions import ASGIAdminError

if TYPE_CHECKING:
    from .views import ViewBase


class RouteView(Route):
    """
    Subclass of `starlette.routing.Route` that includes a reference
    to the view that defines the route.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        view: "ViewBase",
        *,
        methods: Union[list[str], None] = None,
        name: Union[str, None] = None,
        include_in_schema: bool = True,
        middleware: Union[Sequence[Middleware], None] = None,
    ) -> None:
        super().__init__(
            path,
            endpoint,
            methods=methods,
            name=name,
            include_in_schema=include_in_schema,
            middleware=middleware,
        )
        self.view = view


class CurrentRouteNotFound(ASGIAdminError):
    """
    Raised when the current route is not found.
    """

    def __init__(self) -> None:  # pragma: no cover
        super().__init__("Current route not found.")


def _get_current_route(
    routes: list[RouteView], endpoint: Callable[..., Any]
) -> RouteView:
    for route in routes:
        if getattr(route, "endpoint", None) == endpoint:
            return route
        if sub_route := getattr(route, "routes", None):
            return _get_current_route(sub_route, endpoint)
    raise CurrentRouteNotFound()  # pragma: no cover


def get_current_route(request: Request) -> RouteView:
    app: Starlette = request.scope["app"]
    endpoint: Callable[..., Any] = request.scope["endpoint"]
    routes: list[RouteView] = cast(list[RouteView], app.routes)
    return _get_current_route(routes, endpoint)


__all__ = ["RouteView", "get_current_route"]

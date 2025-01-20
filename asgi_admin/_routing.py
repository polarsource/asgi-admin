from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Union

from starlette.applications import Starlette
from starlette.requests import Request

from .exceptions import ASGIAdminError

if TYPE_CHECKING:
    from .views import ViewBase


class CurrentRouteNotFound(ASGIAdminError):
    """
    Raised when the current route is not found.
    """

    def __init__(self) -> None:  # pragma: no cover
        super().__init__("Current route not found.")


def _get_current_route(
    route: Any, endpoint: Callable[..., Any]
) -> Union["ViewBase", None]:
    if getattr(route, "endpoint", None) == endpoint:
        return endpoint  # type: ignore

    for sub_route in getattr(route, "routes", []):
        if current_route := _get_current_route(sub_route, endpoint):
            return current_route

    return None


def get_current_route(request: Request) -> "ViewBase":
    app: Starlette = request.scope["app"]
    endpoint: Callable[..., Any] = request.scope["endpoint"]
    current_route = _get_current_route(app.router, endpoint)
    if current_route is None:
        raise CurrentRouteNotFound()  # pragma: no cover
    return current_route


__all__ = ["get_current_route"]

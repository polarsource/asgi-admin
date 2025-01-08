from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Generic, TypeVar, Union

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Router
from typing_extensions import ParamSpec

from .repository import Model, RepositoryProtocol

Params = ParamSpec("Params")
ReturnValue = TypeVar("ReturnValue")
ViewType = TypeVar("ViewType", bound="ViewBase")
RouteType = Callable[[ViewType, Request], Awaitable[Response]]


def route(
    path: str,
    methods: list[str],
    *,
    name: Union[str, None] = None,
) -> Callable[[RouteType], RouteType]:
    def decorator(func: RouteType) -> RouteType:
        func._route_info = {"path": path, "methods": methods, "name": name}  # type: ignore
        return func

    return decorator


class ViewBase:
    prefix: ClassVar[str] = "/"
    router: Router

    def __init__(self) -> None:
        self.router = Router()
        for attr_name in dir(self):
            attr_value = getattr(self, attr_name)
            if hasattr(attr_value, "_route_info"):
                route_info = attr_value._route_info
                self.router.add_route(
                    route_info["path"],
                    attr_value,
                    methods=route_info["methods"],
                    name=route_info["name"],
                )


class ModelView(ViewBase, Generic[Model]):
    model: ClassVar[type[Any]]
    list_default_limit: ClassVar[int] = 10

    async def get_repository(self, request: Request) -> RepositoryProtocol[Model]:
        raise NotImplementedError()

    @route("/", methods=["GET"])
    async def list(self, request: Request) -> Response:
        offset, limit = self._get_pagination(request)
        repository = await self.get_repository(request)
        items = await repository.list(offset, limit)
        return HTMLResponse(
            f"""
            <html>
                <head>
                    <title>Admin</title>
                </head>
                <body>
                    <h1>Admin</h1>
                    <ul>
                        {"".join(f"<li>{item}</li>" for item in items)}
                    </ul>
                </body>
            </html>
        """
        )

    def _get_pagination(self, request: Request) -> tuple[int, int]:
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", self.list_default_limit))
        return offset, limit

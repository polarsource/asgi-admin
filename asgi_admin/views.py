import urllib
import urllib.parse
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, ClassVar, Generic, TypedDict, TypeVar, Union

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, Router

from ._normalization import class_name_to_url_path
from ._routing import get_current_route
from .exceptions import ASGIAdminConfigurationError
from .repository import Model, RepositoryProtocol
from .templating import templates

ViewType = TypeVar("ViewType", bound="ViewBase")
RouteType = Callable[[ViewType, Request], Awaitable[Response]]


def route(
    path: str,
    methods: list[str],
    *,
    name: Union[str, None] = None,
    index: bool = False,
) -> Callable[[RouteType], RouteType]:
    def decorator(func: RouteType) -> RouteType:
        func._route_info = {  # type: ignore
            "path": path,
            "methods": methods,
            "name": name,
            "index": index,
        }
        return func

    return decorator


class ViewConfigurationError(ASGIAdminConfigurationError):
    """
    Raised when a view is not correctly configured.

    Parameters:
        message: The error message.
        cls: The view class.
    """

    def __init__(
        self,
        message: str,
        cls: type["ViewBase"],
    ) -> None:
        self.cls = cls
        super().__init__(message)


class MissingViewTitleError(ViewConfigurationError):
    """
    Raised when a view is missing a title.

    Parameters:
        cls: The view class.
    """

    def __init__(self, cls: type["ViewBase"]) -> None:
        super().__init__(
            f"The `title` attribute must be set on the view class {cls.__name__}", cls
        )


class MissingViewPrefixError(ViewConfigurationError):
    """
    Raised when a view is missing a prefix.

    Parameters:
        cls: The view class.
    """

    def __init__(self, cls: type["ViewBase"]) -> None:
        super().__init__(
            f"The `prefix` attribute must be set on the view class {cls.__name__}", cls
        )


class ViewBase:
    title: ClassVar[str]
    prefix: ClassVar[str]
    router: Router
    index_route: Route

    def __init_subclass__(cls, **kwargs) -> None:
        if cls.__name__ != "ModelView":
            if not hasattr(cls, "title"):
                raise MissingViewTitleError(cls)
            if not hasattr(cls, "prefix"):
                raise MissingViewPrefixError(cls)
        super().__init_subclass__(**kwargs)

    def __init__(self) -> None:
        routes: list[Route] = []
        for attr_name in dir(self):
            attr_value = getattr(self, attr_name)
            if hasattr(attr_value, "_route_info"):
                route_info = attr_value._route_info
                name = route_info["name"] or f"{self.__class__.__name__}.{attr_name}"
                route = Route(
                    route_info["path"],
                    attr_value,
                    methods=route_info["methods"],
                    name=name,
                )
                routes.append(route)
                if route_info["index"]:
                    index_route = route

        if index_route is None:
            index_route = routes[0]

        self.router = Router(routes=routes)
        self.index_route = index_route


class MissingModelViewModelError(ViewConfigurationError):
    """
    Raised when a model view is missing a model.

    Parameters:
        cls: The model view class.
    """

    def __init__(self, cls: type["ModelView"]) -> None:
        super().__init__(
            f"The `model` attribute must be set on the model view class {cls.__name__}",
            cls,
        )


class MissingModelViewListFieldsError(ViewConfigurationError):
    """
    Raised when a model view is missing a list of fields.

    Parameters:
        cls: The model view class.
    """

    def __init__(self, cls: type["ModelView"]) -> None:
        super().__init__(
            f"The `list_fields` attribute must be set on the model view class {cls.__name__}",
            cls,
        )


class PaginationOutput(TypedDict):
    offset: int
    limit: int
    total: int
    range: tuple[int, int]
    next_route: Union[str, None]
    previous_route: Union[str, None]


class ModelView(ViewBase, Generic[Model]):
    model: ClassVar[type[Any]]
    list_default_limit: ClassVar[int] = 10
    list_fields: ClassVar[Iterable[str]]
    field_labels: ClassVar[dict[str, str]] = {}

    def __init_subclass__(cls, **kwargs):
        if not hasattr(cls, "model"):
            raise MissingModelViewModelError(cls)
        if not hasattr(cls, "list_fields"):
            raise MissingModelViewListFieldsError(cls)
        if not hasattr(cls, "title"):
            cls.title = cls.model.__name__
        if not hasattr(cls, "prefix"):
            cls.prefix = f"/{class_name_to_url_path(cls.model.__name__)}"
        super().__init_subclass__(**kwargs)

    async def get_repository(self, request: Request) -> RepositoryProtocol[Model]:
        raise NotImplementedError()

    @route("/", methods=["GET"], index=True)
    async def list(self, request: Request) -> Response:
        offset, limit = self._get_pagination_input(request)
        repository = await self.get_repository(request)
        total, items = await repository.paginate(offset, limit)
        return templates.TemplateResponse(
            request,
            "views/model/list.html.jinja",
            {
                "page_title": self.title,
                "view": self,
                "items": items,
                "pagination": self._get_pagination_output(
                    request, offset, limit, total
                ),
            },
        )

    def _get_pagination_input(self, request: Request) -> tuple[int, int]:
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", self.list_default_limit))
        return offset, limit

    def _get_pagination_output(
        self, request: Request, offset: int, limit: int, total: int
    ) -> PaginationOutput:
        current_route = get_current_route(request)
        assert current_route is not None

        next_offset = offset + limit
        next_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": next_offset}
        )
        next_route = (
            f"{request.url_for(current_route)}?{next_query_params}"
            if next_offset < total
            else None
        )

        previous_offset = offset - limit
        previous_query_params = urllib.parse.urlencode(
            {**request.query_params, "offset": previous_offset}
        )
        previous_route = (
            f"{request.url_for(current_route)}?{previous_query_params}"
            if previous_offset >= 0
            else None
        )

        return {
            "offset": offset,
            "limit": limit,
            "total": total,
            "range": (offset, min(offset + limit, total)),
            "next_route": next_route,
            "previous_route": previous_route,
        }

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Union

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    PackageLoader,
    select_autoescape,
)
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from .._constants import CONTEXT_CURRENT_ROUTE_KEY, CONTEXT_ROOT_VIEW, SCOPE_ROOT_VIEW
from .._routing import get_current_route

if TYPE_CHECKING:
    from ..views import ViewBase


def keygetter(key: str, d: dict[str, Any]) -> Any:
    return d.get(key)


def untitle(value: str) -> str:
    return value.lower() if value.istitle() else value


def create_environment(
    loaders: Union[Sequence[BaseLoader], None] = None,
) -> Environment:
    env = Environment(
        loader=ChoiceLoader(
            [
                *(loaders or ()),
                PackageLoader("asgi_admin.templating", "templates"),
            ]
        ),
        autoescape=select_autoescape(),
    )
    env.filters["keygetter"] = keygetter
    env.filters["untitle"] = untitle
    return env


def state_context(request: Request) -> dict[str, Any]:
    return {
        CONTEXT_ROOT_VIEW: getattr(request.state, SCOPE_ROOT_VIEW),
    }


def current_route_context(request: Request) -> dict[str, "Union[ViewBase, None]"]:
    return {CONTEXT_CURRENT_ROUTE_KEY: get_current_route(request)}


class Renderer(Jinja2Templates):
    def __init__(self, env: Environment) -> None:
        super().__init__(
            env=env, context_processors=[state_context, current_route_context]
        )

    @classmethod
    def create_with_loaders(cls, loaders: Sequence[BaseLoader]) -> "Renderer":
        return cls(env=create_environment(loaders))


default_renderer = Renderer(create_environment())

__all__ = ["create_environment", "Renderer", "default_renderer"]

from collections.abc import Awaitable, Callable
from typing import TypeVar

from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


def wrap_to_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """
    Wrap a synchronous function to an asynchronous function.

    Parameters:
        func: The synchronous function to wrap.

    Returns:
        The function wrapped as an asynchronous function.
    """

    async def async_func(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)

    return async_func


__all__ = ["wrap_to_async"]

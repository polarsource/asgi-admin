from typing import TypedDict, Union

from starlette.datastructures import URL
from typing_extensions import NotRequired


class BreadcrumbItem(TypedDict):
    label: str
    url: Union[str, URL]
    active: NotRequired[bool]

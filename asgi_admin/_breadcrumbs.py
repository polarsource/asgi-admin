from typing import TypedDict, Union

from starlette.datastructures import URL


class BreadcrumbItem(TypedDict):
    label: str
    url: Union[str, URL]

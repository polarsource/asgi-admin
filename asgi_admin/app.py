from typing import ClassVar

from starlette.routing import Router

from asgi_admin.views import ViewBase


class AdminBase:
    views: ClassVar[list[ViewBase]]

    def __init__(self) -> None:
        router = Router()
        for view in self.views:
            router.mount(view.prefix, view.router)
        self.router = router

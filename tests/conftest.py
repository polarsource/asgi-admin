from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from starlette.applications import Starlette

from asgi_admin.admin import AdminBase

from .app import MyModelView


class MyAdmin(AdminBase):
    views = [MyModelView()]


@pytest.fixture
def app() -> Starlette:
    app = Starlette()
    app.mount("/admin", MyAdmin())
    return app


@pytest_asyncio.fixture
async def client(app: Starlette) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(
            base_url="http://admin", transport=httpx.ASGITransport(manager.app)
        ) as client:
            yield client

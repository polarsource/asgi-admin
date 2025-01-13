from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from starlette.applications import Starlette

from .app import admin


@pytest.fixture
def app() -> Starlette:
    app = Starlette()
    app.mount("/admin", admin.router)
    return app


@pytest_asyncio.fixture
async def client(app: Starlette) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(
            base_url="http://admin", transport=httpx.ASGITransport(manager.app)
        ) as client:
            yield client

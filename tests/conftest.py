import datetime
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from starlette.applications import Starlette

from .app import MyModel, MyModelMapping, create_admin


@pytest.fixture
def items() -> MyModelMapping:
    return {
        f"item_{i}": MyModel(
            id=f"item_{i}",
            label=f"Item {i}",
            created_at=datetime.datetime.now(),
        )
        for i in range(10)
    }


@pytest.fixture
def app(items: MyModelMapping) -> Starlette:
    app = Starlette()
    admin = create_admin(items)
    app.mount("/admin", admin.route)
    return app


@pytest_asyncio.fixture
async def client(app: Starlette) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        async with httpx.AsyncClient(
            base_url="http://admin", transport=httpx.ASGITransport(manager.app)
        ) as client:
            yield client

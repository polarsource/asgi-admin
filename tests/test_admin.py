from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from bs4 import BeautifulSoup
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


@pytest.mark.asyncio
async def test_app(client: httpx.AsyncClient) -> None:
    response = await client.get("/admin/my-model/")
    assert response.status_code == 200

    parsed = BeautifulSoup(response.text, "html.parser")
    tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
    assert len(tbody_tr_items) == 10

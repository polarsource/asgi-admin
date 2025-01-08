from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from bs4 import BeautifulSoup
from starlette.applications import Starlette

from asgi_admin.app import AdminBase

from .conftest import MyModelView


class MyAdmin(AdminBase):
    views = [MyModelView()]


@pytest.fixture
def app() -> Starlette:
    app = Starlette()
    app.mount("/admin", MyAdmin().router)
    return app


@pytest_asyncio.fixture
async def client(app: Starlette) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url="http://admin", transport=httpx.ASGITransport(app)
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_app(client: httpx.AsyncClient) -> None:
    response = await client.get("/admin/")
    assert response.status_code == 200

    parsed = BeautifulSoup(response.text, "html.parser")
    li_items = parsed.find_all("li")
    assert len(li_items) == 10

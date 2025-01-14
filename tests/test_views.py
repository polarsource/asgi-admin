import httpx
import pytest
from bs4 import BeautifulSoup

from asgi_admin.views import ModelViewList, NotTiedToModelViewSetError

from .app import MyModel, MyModelMapping


@pytest.fixture
def first_item(items: MyModelMapping) -> MyModel:
    return list(items.values())[0]


@pytest.mark.asyncio
class TestModelViewList:
    async def test_orphan_view(self) -> None:
        with pytest.raises(NotTiedToModelViewSetError):
            view = ModelViewList[MyModel](
                title="My Model", fields=["id", "label"], path="/", name="list"
            )
            view.viewset

    async def test_basic(
        self, client: httpx.AsyncClient, items: MyModelMapping
    ) -> None:
        response = await client.get("/admin/my-model/")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == len(items)

    async def test_pagination(
        self, client: httpx.AsyncClient, items: MyModelMapping
    ) -> None:
        response = await client.get(
            "/admin/my-model/", params={"limit": 3, "offset": 3}
        )
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == 3
        td_id = tbody_tr_items[0].find_all("td")[1]
        assert td_id.text.strip() == items[list(items.keys())[3]].id

    async def test_sorting(
        self, client: httpx.AsyncClient, items: MyModelMapping
    ) -> None:
        response = await client.get("/admin/my-model/", params={"sorting": "-label"})
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == len(items)
        td_id = tbody_tr_items[0].find_all("td")[1]
        assert td_id.text.strip() == items[list(items.keys())[-1]].id

    async def test_query(self, client: httpx.AsyncClient, first_item: MyModel) -> None:
        response = await client.get("/admin/my-model/", params={"query": "item 0"})
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == 1
        td_id = tbody_tr_items[0].find_all("td")[1]
        assert td_id.text.strip() == first_item.id


@pytest.mark.asyncio
class TestModelViewEdit:
    async def test_not_found(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/not-existing")
        assert response.status_code == 404

    async def test_get(self, client: httpx.AsyncClient, first_item: MyModel) -> None:
        response = await client.get(f"/admin/my-model/{first_item.id}")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        form = parsed.find_all("form")[0]
        assert form["method"] == "POST"
        assert form["action"].endswith(f"/admin/my-model/{first_item.id}")

    async def test_post_invalid(
        self, client: httpx.AsyncClient, first_item: MyModel, items: MyModelMapping
    ) -> None:
        response = await client.post(
            f"/admin/my-model/{first_item.id}", data={"label": ""}
        )
        assert response.status_code == 400

        assert items[first_item.id].label == first_item.label

    async def test_post_valid(
        self, client: httpx.AsyncClient, first_item: MyModel, items: MyModelMapping
    ) -> None:
        response = await client.post(
            f"/admin/my-model/{first_item.id}", data={"label": "Updated Label"}
        )
        assert response.status_code == 200

        assert items[first_item.id].label == "Updated Label"


@pytest.mark.asyncio
class TestModelViewCustom:
    async def test_basic(self, client: httpx.AsyncClient, first_item: MyModel) -> None:
        response = await client.get("/admin/my-model/custom")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        custom_div = parsed.find("div", {"id": "custom"})
        assert custom_div is not None
        assert custom_div.text.strip() == "Hello!"


@pytest.mark.asyncio
class TestModelViewItemCustom:
    async def test_not_found(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/not-existing/custom-item")
        assert response.status_code == 404

    async def test_basic(self, client: httpx.AsyncClient, first_item: MyModel) -> None:
        response = await client.get(f"/admin/my-model/{first_item.id}/custom-item")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        custom_div = parsed.find("div", {"id": "custom"})
        assert custom_div is not None
        assert custom_div.text.strip() == f"Showing {first_item.label}"

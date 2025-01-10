import httpx
import pytest
from bs4 import BeautifulSoup

from asgi_admin.views import (
    MissingModelViewListFieldsError,
    MissingModelViewModelError,
    MissingViewPrefixError,
    MissingViewTitleError,
    ModelView,
    ViewBase,
)

from .app import ITEMS, MyModel

FIRST_ITEM_ID = list(ITEMS.keys())[0]
FIRST_ITEM = ITEMS[FIRST_ITEM_ID]


class TestBaseViewConfigurationError:
    def test_missing_title(self) -> None:
        with pytest.raises(MissingViewTitleError):

            class MyView(ViewBase): ...

    def test_missing_prefix(self) -> None:
        with pytest.raises(MissingViewPrefixError):

            class MyView(ViewBase):
                title = "My View"


class TestModelViewConfigurationError:
    def test_missing_model(self) -> None:
        with pytest.raises(MissingModelViewModelError):

            class MyModelView(ModelView): ...

    def test_missing_list_fields(self) -> None:
        with pytest.raises(MissingModelViewListFieldsError):

            class MyModelView(ModelView):
                model = MyModel


@pytest.mark.asyncio
class TestModelViewList:
    async def test_basic(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == len(ITEMS)

    async def test_sorting(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/", params={"sorting": "-label"})
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == len(ITEMS)
        td_id = tbody_tr_items[0].find_all("td")[0]
        assert td_id.text == ITEMS[list(ITEMS.keys())[-1]].id

    async def test_query(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/", params={"query": "item 0"})
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        tbody_tr_items = parsed.find_all("tbody")[0].find_all("tr")
        assert len(tbody_tr_items) == 1
        td_id = tbody_tr_items[0].find_all("td")[0]
        assert td_id.text == FIRST_ITEM.id


@pytest.mark.asyncio
class TestModelViewEdit:
    async def test_not_found(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/admin/my-model/not-existing")
        assert response.status_code == 404

    async def test_get(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"/admin/my-model/{FIRST_ITEM_ID}")
        assert response.status_code == 200

        parsed = BeautifulSoup(response.text, "html.parser")
        form = parsed.find_all("form")[0]
        assert form["method"] == "POST"
        assert form["action"].endswith(f"/admin/my-model/{FIRST_ITEM_ID}")

    async def test_post_invalid(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"/admin/my-model/{FIRST_ITEM_ID}", data={"label": ""}
        )
        assert response.status_code == 400

        assert ITEMS[FIRST_ITEM_ID].label == FIRST_ITEM.label

    async def test_post_valid(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"/admin/my-model/{FIRST_ITEM_ID}", data={"label": "Updated Label"}
        )
        assert response.status_code == 200

        assert ITEMS[FIRST_ITEM_ID].label == "Updated Label"

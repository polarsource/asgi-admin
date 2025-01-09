from starlette.applications import Starlette

from .conftest import MyAdmin

app = Starlette()
app.mount("/admin", MyAdmin())

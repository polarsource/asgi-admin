import datetime
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from asgi_admin.integrations.sqlalchemy import RepositoryBase
from asgi_admin.repository import SortingOrder


class Base(DeclarativeBase):
    pass


class MyModel(Base):
    __tablename__ = "my_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


class MyModelRepository(RepositoryBase):
    model = MyModel


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
class TestRepositoryList:
    async def test_basic(self, session: AsyncSession) -> None:
        item1 = MyModel(label="Item 1")
        session.add(item1)
        item2 = MyModel(label="Item 2")
        session.add(item2)
        item3 = MyModel(label="Item 3")
        session.add(item3)
        await session.flush()

        repository = MyModelRepository(session)

        count, items = await repository.list([], 0, 10)
        assert count == 3
        assert items == [item1, item2, item3]

    async def test_offset_limit(self, session: AsyncSession) -> None:
        item1 = MyModel(label="Item 1")
        session.add(item1)
        item2 = MyModel(label="Item 2")
        session.add(item2)
        item3 = MyModel(label="Item 3")
        session.add(item3)
        await session.flush()

        repository = MyModelRepository(session)

        count, items = await repository.list([], 1, 1)
        assert count == 3
        assert items == [item2]

    async def test_sorting(self, session: AsyncSession) -> None:
        item1 = MyModel(label="Item 1")
        session.add(item1)
        item2 = MyModel(label="Item 2")
        session.add(item2)
        item3 = MyModel(label="Item 3")
        session.add(item3)
        await session.flush()

        repository = MyModelRepository(session)

        count, items = await repository.list([("label", SortingOrder.DESC)], 0, 10)
        assert count == 3
        assert items == [item3, item2, item1]

    async def test_query(self, session: AsyncSession) -> None:
        item1 = MyModel(label="Item A")
        session.add(item1)
        item2 = MyModel(label="Item B")
        session.add(item2)
        item3 = MyModel(label="Item C")
        session.add(item3)
        await session.flush()

        repository = MyModelRepository(session)

        count, items = await repository.list(
            [], 0, 10, query="b", query_fields=["label"]
        )
        assert count == 1
        assert items == [item2]

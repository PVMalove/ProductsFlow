from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.http.dependencies import get_catalog_client
from infrastructure.db.entity_configurations.models import Base
from infrastructure.db.session import get_db_session
from infrastructure.security.auth import get_identity_client
from tests.integration.fake_identity_client import FakeIdentityClient
from tests.unit.fake_catalog_client import FakeCatalogClient


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """test_support.postgres не запускает миграции (у каждого сервиса своя
    alembic-история) — здесь создаём схему напрямую из ORM-метаданных, тем же
    приёмом, что уже применяет catalog/payment-service."""
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def saga_session_factory(
    db_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """issue #375: фабрика сессий для worker-адаптеров, которые сами
    открывают `session_factory()` + `session.begin()`. Все сессии делят одно
    соединение во внешней транзакции (`create_savepoint`) — `begin()`
    адаптера становится savepoint'ом, а откат в конце теста оставляет базу
    чистой, тот же приём, что `db_session`."""
    async with db_engine.connect() as connection:
        await connection.begin()
        try:
            yield async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
        finally:
            await connection.rollback()


@pytest.fixture
def identity_client() -> FakeIdentityClient:
    return FakeIdentityClient()


@pytest.fixture
def catalog_client() -> FakeCatalogClient:
    return FakeCatalogClient()


@pytest_asyncio.fixture
async def cart_client(
    db_session: AsyncSession,
    identity_client: FakeIdentityClient,
    catalog_client: FakeCatalogClient,
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI-тестклиент (ADR 0013, Seam A) поверх настоящего Postgres
    (`db_session`, savepoint на тест) и фейковых identity/catalog клиентов —
    HTTP-слой прогоняется целиком, identity-service/catalog-service — нет
    (DoD п.10, issue #372 seam #10)."""
    from api.http.main import app

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_identity_client] = lambda: identity_client
    app.dependency_overrides[get_catalog_client] = lambda: catalog_client
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://order"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# Импорт регистрирует InventoryModel/InventoryAuditLog на общем Base.metadata
# (тот же Base, что и kernel_platform.OutboxMessage) — сам модуль напрямую
# не используется, только его сторонний эффект на импорте.
from infrastructure import db as _db  # noqa: F401
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db import processed_messages as _processed_messages  # noqa: F401
from infrastructure.db.session import get_db_session
from infrastructure.security.auth import get_identity_client
from tests.integration.fake_identity_client import FakeIdentityClient


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """test_support.postgres не запускает миграции (у каждого сервиса своя
    alembic-история) — здесь создаём схему напрямую из ORM-метаданных, тем
    же приёмом, что уже применяет catalog-service."""
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def identity_client() -> FakeIdentityClient:
    return FakeIdentityClient()


@pytest_asyncio.fixture
async def inventory_client(
    db_session: AsyncSession, identity_client: FakeIdentityClient
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI-тестклиент (ADR 0013, Seam A) поверх настоящего Postgres
    (`db_session`, savepoint на тест) и фейкового identity-клиента — HTTP-слой
    прогоняется целиком, identity-service — нет."""
    from api.main import app

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_identity_client] = lambda: identity_client
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://inventory"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

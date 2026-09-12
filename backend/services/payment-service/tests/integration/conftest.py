from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from infrastructure.db.entity_configurations.models import Base
from infrastructure.db.session import get_db_session
from infrastructure.psp.mock_psp_adapter import MockPspAdapter
from infrastructure.security.auth import get_identity_client
from tests.integration.fake_identity_client import FakeIdentityClient


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """test_support.postgres не запускает миграции (у каждого сервиса своя
    alembic-история) — здесь создаём схему напрямую из ORM-метаданных, тем же
    приёмом, что уже применяет catalog/inventory-service."""
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


class SpyPspAdapter(MockPspAdapter):
    """`MockPspAdapter` с подсчётом вызовов (issue #368, Seams for TDD #7) —
    тесты используют его, чтобы утверждать «повторный Idempotency-Key не
    переспрашивает PSP», не подменяя детерминированное поведение адаптера."""

    def __init__(self) -> None:
        self.authorize_calls: list[tuple[str, int]] = []
        self.capture_calls: list[str] = []

    async def authorize(self, payment_method_token: str, amount: int):  # type: ignore[override]
        self.authorize_calls.append((payment_method_token, amount))
        return await super().authorize(payment_method_token, amount)

    async def capture(self, payment_method_token: str):  # type: ignore[override]
        self.capture_calls.append(payment_method_token)
        return await super().capture(payment_method_token)


@pytest.fixture
def psp_client() -> SpyPspAdapter:
    return SpyPspAdapter()


@pytest_asyncio.fixture
async def payment_client(
    db_session: AsyncSession,
    identity_client: FakeIdentityClient,
    psp_client: SpyPspAdapter,
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI-тестклиент (ADR 0013, Seam A) поверх настоящего Postgres
    (`db_session`, savepoint на тест), фейкового identity-клиента и реального
    (детерминированного, без I/O) `MockPspAdapter` — HTTP-слой прогоняется
    целиком, identity-service — нет, реального PSP не существует (DoD п.7)."""
    from api.dependencies import get_psp_client
    from api.main import app

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_identity_client] = lambda: identity_client
    app.dependency_overrides[get_psp_client] = lambda: psp_client
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://payment"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

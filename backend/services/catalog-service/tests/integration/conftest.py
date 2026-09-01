from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# Импорт регистрирует ProductModel/ProductAuditLog на общем Base.metadata
# (тот же Base, что и kernel_platform.OutboxMessage) — сам модуль напрямую
# не используется, только его сторонний эффект на импорте.
from infrastructure import db as _db  # noqa: F401
from infrastructure.db import owner_read_model as _owner_read_model  # noqa: F401
from infrastructure.db.session import get_db_session
from infrastructure.security.auth import get_identity_gateway
from infrastructure.storage import get_storage
from tests.integration.fake_identity_gateway import FakeIdentityGateway


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """test_support.postgres не запускает миграции (у каждого сервиса своя
    alembic-история) — здесь создаём схему напрямую из ORM-метаданных, тем
    же приёмом, что уже применяет identity-service (tests/integration/
    test_outbox_publisher.py::_outbox_table)."""
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def identity_gateway() -> FakeIdentityGateway:
    return FakeIdentityGateway()


class FakeImageStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.deleted: list[tuple[str, str]] = []

    async def put_object(
        self, bucket_name: str, key: str, body: bytes, content_type: str
    ) -> None:
        self.objects[(bucket_name, key)] = (body, content_type)

    async def delete_object(self, bucket_name: str, key: str) -> None:
        self.deleted.append((bucket_name, key))
        self.objects.pop((bucket_name, key), None)

    async def build_presigned_url(
        self, bucket_name: str, key: str, expires_in: int = 3600
    ) -> str:
        return f"http://storage/{bucket_name}/{key}?X-Amz-Signature=fake"


@pytest.fixture
def image_storage() -> FakeImageStorage:
    return FakeImageStorage()


@pytest_asyncio.fixture
async def catalog_client(
    db_session: AsyncSession,
    identity_gateway: FakeIdentityGateway,
    image_storage: FakeImageStorage,
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI-тестклиент (ADR 0018, Seam A) поверх настоящего Postgres
    (`db_session`, savepoint на тест) и фейкового `IdentityGateway` —
    HTTP-слой прогоняется целиком, identity-service — нет."""
    from presentation.main import app

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_identity_gateway] = lambda: identity_gateway
    app.dependency_overrides[get_storage] = lambda: image_storage
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://catalog"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

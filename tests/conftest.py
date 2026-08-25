from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import URL, ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from app.db import _run_upgrade, get_session
from app.main import app
from app.settings import settings
from app.storage import get_storage

POSTGRES_IMAGE = "postgres:18.0"
API_PREFIX = "/api/v1"
API_ROUTE_PREFIXES = ("/auth", "/products", "/users")

# Тот же тег, что у minio_dev/minio_prod в docker-compose.yml.
MINIO_IMAGE = "minio/minio:RELEASE.2025-04-22T22-12-26Z"
MINIO_PORT = 9000
MINIO_TEST_USER = "test-minio-admin"
MINIO_TEST_PASSWORD = "test-minio-secret"
MINIO_TEST_BUCKET = "product-chunks-test"


class ApiClient(AsyncClient):
    async def request(
        self, method: str, url: URL | str, *args: Any, **kwargs: Any
    ) -> Response:
        url_str = str(url)
        if not url_str.startswith(("http://", "https://")):
            normalized_url = url_str if url_str.startswith("/") else f"/{url_str}"
            is_api_route = any(
                normalized_url == route_prefix
                or normalized_url.startswith(f"{route_prefix}/")
                for route_prefix in API_ROUTE_PREFIXES
            )
            if is_api_route and not normalized_url.startswith(f"{API_PREFIX}/"):
                normalized_url = f"{API_PREFIX}{normalized_url}"
            url_str = normalized_url
        return await super().request(method, url_str, *args, **kwargs)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def minio_container() -> Iterator[DockerContainer]:
    container = (
        DockerContainer(MINIO_IMAGE)
        .with_exposed_ports(MINIO_PORT)
        .with_env("MINIO_ROOT_USER", MINIO_TEST_USER)
        .with_env("MINIO_ROOT_PASSWORD", MINIO_TEST_PASSWORD)
        .with_command(f"server /data --address :{MINIO_PORT}")
        .waiting_for(HttpWaitStrategy(MINIO_PORT, "/minio/health/live"))
    )
    with container as started:
        yield started


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def minio_ready(minio_container: DockerContainer) -> None:
    """Настраивает settings на контейнерный MinIO и создаёт бакет картинок
    товара — образы, реально пишущие/удаляющие объекты в S3 (в отличие от
    GET, который только собирает URL-строку), просят эту фикстуру явно."""
    host = minio_container.get_container_host_ip()
    port = minio_container.get_exposed_port(MINIO_PORT)
    endpoint = f"http://{host}:{port}"
    settings.minio_endpoint = endpoint
    settings.minio_public_endpoint = endpoint
    settings.minio_root_user = MINIO_TEST_USER
    settings.minio_root_password = MINIO_TEST_PASSWORD
    settings.minio_bucket_name_product = MINIO_TEST_BUCKET
    await get_storage().ensure_bucket_exists(MINIO_TEST_BUCKET)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(
    postgres_container: PostgresContainer,
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_upgrade)
        await connection.commit()
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    try:
        async with ApiClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        del app.dependency_overrides[get_session]

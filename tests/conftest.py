from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.db import _run_upgrade, get_session
from app.main import app

POSTGRES_IMAGE = "postgres:18.0"
API_PREFIX = "/api/v1"
API_ROUTE_PREFIXES = ("/auth", "/products", "/users")


class ApiClient(AsyncClient):
    async def request(
        self, method: str, url: str, *args: Any, **kwargs: Any
    ) -> Response:
        if not url.startswith(("http://", "https://")):
            normalized_url = url if url.startswith("/") else f"/{url}"
            is_api_route = any(
                normalized_url == route_prefix
                or normalized_url.startswith(f"{route_prefix}/")
                for route_prefix in API_ROUTE_PREFIXES
            )
            if is_api_route and not normalized_url.startswith(f"{API_PREFIX}/"):
                normalized_url = f"{API_PREFIX}{normalized_url}"
            url = normalized_url
        return await super().request(method, url, *args, **kwargs)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container


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

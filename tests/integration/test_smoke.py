import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import User, UserAuditLog

# db_session/client bind to the session-scoped Postgres engine, so the test
# itself must run on that same event loop (asyncpg connections are loop-bound).
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health_check_responds_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_insert_and_rollback_isolates_writes_between_transactions(
    db_engine: AsyncEngine,
) -> None:
    # Reproduces the db_session fixture's begin+SAVEPOINT+rollback dance
    # directly against db_engine (rather than using the db_session fixture
    # itself), so this test can trigger the rollback mid-test and check its
    # effect on a second, independent connection — proving the isolation
    # mechanism actually discards writes, not just that another transaction
    # can't see uncommitted ones.
    def _count(connection: Connection) -> tuple[int | None, int | None]:
        users = connection.execute(select(func.count()).select_from(User)).scalar()
        audit_rows = connection.execute(
            select(func.count()).select_from(UserAuditLog)
        ).scalar()
        return users, audit_rows

    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        session.add(User(username="smoke-user", password_hash="hash"))
        await session.flush()

        user_count, audit_count = await connection.run_sync(_count)
        assert (user_count, audit_count) == (1, 1)

        await session.close()
        await connection.rollback()

    async with db_engine.connect() as connection:
        user_count, audit_count = await connection.run_sync(_count)

    assert (user_count, audit_count) == (0, 0)

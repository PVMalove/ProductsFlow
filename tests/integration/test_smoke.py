import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserAuditLog

# db_session/client bind to the session-scoped Postgres engine, so the test
# itself must run on that same event loop (asyncpg connections are loop-bound).
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health_check_responds_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_a_insert_is_visible_within_its_own_transaction(
    db_session: AsyncSession,
) -> None:
    db_session.add(User(username="smoke-user", password_hash="hash"))
    await db_session.flush()

    count = await db_session.scalar(select(func.count()).select_from(User))

    assert count == 1


async def test_b_previous_tests_insert_and_its_audit_row_were_rolled_back(
    db_session: AsyncSession,
) -> None:
    # Relies on running after test_a in the same session: proves that the
    # db_session fixture's rollback-per-test actually discards writes
    # (including the audit-log insert triggered by the User insert above),
    # rather than merely relying on cross-transaction isolation.
    user_count = await db_session.scalar(select(func.count()).select_from(User))
    audit_count = await db_session.scalar(
        select(func.count()).select_from(UserAuditLog)
    )

    assert user_count == 0
    assert audit_count == 0

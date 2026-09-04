import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.owner_read_model import (
    get_owner_read_model,
    upsert_owner_read_model,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_returns_none_when_row_is_missing(db_session: AsyncSession) -> None:
    assert await get_owner_read_model(db_session, uuid.uuid4()) is None


async def test_upsert_creates_a_row_when_missing(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()

    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=0,
    )

    row = await get_owner_read_model(db_session, user_id)
    assert row is not None
    assert row.role == "user"
    assert row.is_active is True
    assert row.last_applied_outbox_id == 0


async def test_upsert_applies_a_newer_version_over_an_older_one(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=1,
    )

    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=False,
        last_applied_outbox_id=2,
    )

    row = await get_owner_read_model(db_session, user_id)
    assert row is not None
    assert row.is_active is False
    assert row.last_applied_outbox_id == 2


async def test_upsert_ignores_an_older_version_arriving_after_a_newer_one(
    db_session: AsyncSession,
) -> None:
    """Гонка доставки (ADR 0011, находки #64 по aio-pika): более старое
    событие, применённое после более нового, не должно откатывать строку."""
    user_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=False,
        last_applied_outbox_id=5,
    )

    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=3,
    )

    row = await get_owner_read_model(db_session, user_id)
    assert row is not None
    assert row.is_active is False
    assert row.last_applied_outbox_id == 5


async def test_cold_start_sentinel_loses_to_any_real_event(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=0,
    )

    await upsert_owner_read_model(
        db_session,
        user_id=user_id,
        role="admin",
        is_active=True,
        last_applied_outbox_id=1,
    )

    row = await get_owner_read_model(db_session, user_id)
    assert row is not None
    assert row.role == "admin"
    assert row.last_applied_outbox_id == 1

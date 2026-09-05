import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.search_owner_state import (
    get_search_owner_state,
    upsert_search_owner_state,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_returns_none_when_row_is_missing(db_session: AsyncSession) -> None:
    assert await get_search_owner_state(db_session, uuid.uuid4()) is None


async def test_upsert_creates_a_row_when_missing(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()

    applied = await upsert_search_owner_state(
        db_session,
        user_id=user_id,
        is_active=True,
        last_applied_outbox_id=1,
    )

    row = await get_search_owner_state(db_session, user_id)
    assert applied is True
    assert row is not None
    assert row.is_active is True
    assert row.last_applied_outbox_id == 1


async def test_upsert_applies_a_newer_version_over_an_older_one(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=True, last_applied_outbox_id=1
    )

    applied = await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=False, last_applied_outbox_id=2
    )

    row = await get_search_owner_state(db_session, user_id)
    assert applied is True
    assert row is not None
    assert row.is_active is False
    assert row.last_applied_outbox_id == 2


async def test_upsert_ignores_a_duplicate_of_the_same_version(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=False, last_applied_outbox_id=5
    )

    applied = await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=True, last_applied_outbox_id=5
    )

    row = await get_search_owner_state(db_session, user_id)
    assert applied is False
    assert row is not None
    assert row.is_active is False
    assert row.last_applied_outbox_id == 5


async def test_upsert_ignores_an_older_version_arriving_after_a_newer_one(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=False, last_applied_outbox_id=5
    )

    applied = await upsert_search_owner_state(
        db_session, user_id=user_id, is_active=True, last_applied_outbox_id=3
    )

    row = await get_search_owner_state(db_session, user_id)
    assert applied is False
    assert row is not None
    assert row.is_active is False
    assert row.last_applied_outbox_id == 5

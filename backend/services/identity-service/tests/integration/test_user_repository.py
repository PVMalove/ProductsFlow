import uuid
from collections.abc import AsyncIterator
from contextvars import Token
from typing import Any

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from observability.context import actor_id_var
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from domain.email import Email
from domain.user import User
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db import models as _models  # noqa: F401
from infrastructure.db.audit import UserAuditAction, UserAuditLog
from infrastructure.db.models import UserModel
from infrastructure.db.unit_of_work import SqlIdentityUnitOfWork

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def test_add_persists_user_and_register_event_atomically(
    db_session: AsyncSession, _schema: None
) -> None:
    result = User.register(Email("user@example.com"), "hashed-password")
    assert result.is_ok

    uow = SqlIdentityUnitOfWork(db_session)
    async with uow:
        await uow.users.add(result.value)
        await uow.commit()

    stored = await uow.users.get_by_id(result.value.id)
    assert stored is not None
    assert stored.email == Email("user@example.com")
    assert stored.password_hash == "hashed-password"

    outbox_rows = await db_session.scalars(
        select(OutboxMessage).where(OutboxMessage.aggregate_id == result.value.id.value)
    )
    rows = list(outbox_rows.all())
    assert len(rows) == 1
    assert rows[0].event_type == "user.registered.v1"
    assert rows[0].payload["email"] == "user@example.com"


async def _create_user(uow: SqlIdentityUnitOfWork, email: str) -> User:
    result = User.register(Email(email), "hashed-password")
    assert result.is_ok
    async with uow:
        await uow.users.add(result.value)
        await uow.commit()
    return result.value


async def _rows_for(session: AsyncSession, model: Any, user_id: uuid.UUID) -> list[Any]:
    result = await session.scalars(
        select(model).where(model.user_id == user_id).order_by(model.id)
    )
    return list(result.all())


async def _outbox_rows_for(
    session: AsyncSession, aggregate_id: uuid.UUID
) -> list[OutboxMessage]:
    result = await session.scalars(
        select(OutboxMessage)
        .where(OutboxMessage.aggregate_id == aggregate_id)
        .order_by(OutboxMessage.id)
    )
    return list(result.all())


async def test_save_writes_password_change_to_audit_and_outbox(
    db_session: AsyncSession, _schema: None
) -> None:
    uow = SqlIdentityUnitOfWork(db_session)
    user = await _create_user(uow, "password@example.com")
    loaded = await uow.users.get_by_id(user.id)
    assert loaded is not None
    loaded.pull_events()

    result = loaded.change_password("new-hashed-password")
    assert result.is_ok
    async with uow:
        await uow.users.save(loaded)
        await uow.commit()

    audit_rows = await _rows_for(db_session, UserAuditLog, user.id.value)
    assert [row.action for row in audit_rows] == [
        UserAuditAction.REGISTERED,
        UserAuditAction.PASSWORD_CHANGED,
    ]
    outbox_rows = await _outbox_rows_for(db_session, user.id.value)
    assert [row.event_type for row in outbox_rows] == [
        "user.registered.v1",
        "user.password_changed.v1",
    ]


async def test_save_audits_deactivation_and_activation(
    db_session: AsyncSession, _schema: None
) -> None:
    uow = SqlIdentityUnitOfWork(db_session)
    user = await _create_user(uow, "activation@example.com")
    loaded = await uow.users.get_by_id(user.id)
    assert loaded is not None
    loaded.pull_events()

    assert loaded.deactivate().is_ok
    async with uow:
        await uow.users.save(loaded)
        await uow.commit()
    loaded = await uow.users.get_by_id(user.id)
    assert loaded is not None
    assert loaded.activate().is_ok
    async with uow:
        await uow.users.save(loaded)
        await uow.commit()

    audit_rows = await _rows_for(db_session, UserAuditLog, user.id.value)
    assert [row.action for row in audit_rows] == [
        UserAuditAction.REGISTERED,
        UserAuditAction.DEACTIVATED,
        UserAuditAction.ACTIVATED,
    ]
    outbox_rows = await _outbox_rows_for(db_session, user.id.value)
    assert [row.event_type for row in outbox_rows] == [
        "user.registered.v1",
        "user.deactivated.v1",
        "user.activated.v1",
    ]


async def test_audit_uses_current_actor_from_request_context(
    db_session: AsyncSession, _schema: None
) -> None:
    uow = SqlIdentityUnitOfWork(db_session)
    actor = await _create_user(uow, "actor@example.com")
    target = await _create_user(uow, "target@example.com")
    loaded = await uow.users.get_by_id(target.id)
    assert loaded is not None
    loaded.pull_events()

    token: Token[int | str | None] = actor_id_var.set(str(actor.id.value))
    try:
        assert loaded.deactivate().is_ok
        async with uow:
            await uow.users.save(loaded)
            await uow.commit()
    finally:
        actor_id_var.reset(token)

    audit_rows = await _rows_for(db_session, UserAuditLog, target.id.value)
    assert audit_rows[-1].actor_user_id == actor.id.value


async def test_uow_rolls_back_multiple_user_writes_and_their_outbox_rows(
    db_session: AsyncSession, _schema: None
) -> None:
    first = User.register(Email("first@example.com"), "hashed-password")
    second = User.register(Email("second@example.com"), "hashed-password")
    assert first.is_ok
    assert second.is_ok

    uow = SqlIdentityUnitOfWork(db_session)
    with pytest.raises(RuntimeError, match="second mutation failed"):
        async with uow:
            await uow.users.add(first.value)
            await uow.users.add(second.value)
            raise RuntimeError("second mutation failed")

    db_session.expunge_all()
    assert await db_session.scalar(select(UserModel.id)) is None
    assert await db_session.scalar(select(OutboxMessage.id)) is None

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

from domain.entities.user import User
from domain.value_objects.email import Email
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db.audit import UserAuditAction, UserAuditLog
from infrastructure.db.entity_configurations.models import UserModel
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


class _CreateTwoUsersHandler:
    """Integration seam for the command-side transaction boundary."""

    def __init__(self, uow: SqlIdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, first: User, second: User, *, fail_after_writes: bool = False
    ) -> None:
        async with self._uow:
            await self._uow.users.add(first)
            await self._uow.users.add(second)
            if fail_after_writes:
                raise RuntimeError("second mutation failed")
            await self._uow.commit()


async def test_add_persists_user_and_register_event_atomically(
    db_session: AsyncSession, _schema: None
) -> None:
    result = User.register(Email.create("user@example.com").value, "hashed-password")
    assert result.is_ok

    uow = SqlIdentityUnitOfWork(db_session)
    async with uow:
        await uow.users.add(result.value)
        await uow.commit()

    stored = await uow.users.get_by_id(result.value.id)
    assert stored is not None
    assert stored.email == Email.create("user@example.com").value
    assert stored.password_hash == "hashed-password"

    outbox_rows = await db_session.scalars(
        select(OutboxMessage).where(OutboxMessage.aggregate_id == result.value.id.value)
    )
    rows = list(outbox_rows.all())
    assert len(rows) == 1
    assert rows[0].event_type == "user.registered.v1"
    assert rows[0].payload["email"] == "user@example.com"


async def _create_user(uow: SqlIdentityUnitOfWork, email: str) -> User:
    result = User.register(Email.create(email).value, "hashed-password")
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


async def test_handler_rolls_back_multiple_user_writes_and_their_outbox_rows(
    db_session: AsyncSession, _schema: None
) -> None:
    first = User.register(Email.create("first@example.com").value, "hashed-password")
    second = User.register(Email.create("second@example.com").value, "hashed-password")
    assert first.is_ok
    assert second.is_ok

    handler = _CreateTwoUsersHandler(SqlIdentityUnitOfWork(db_session))
    with pytest.raises(RuntimeError, match="second mutation failed"):
        await handler.execute(first.value, second.value, fail_after_writes=True)

    db_session.expunge_all()
    assert await db_session.scalar(select(UserModel.id)) is None
    assert await db_session.scalar(select(OutboxMessage.id)) is None


async def test_handler_commits_multiple_user_writes_with_outbox_rows(
    db_session: AsyncSession, _schema: None
) -> None:
    first = User.register(Email.create("first@example.com").value, "hashed-password")
    second = User.register(Email.create("second@example.com").value, "hashed-password")
    assert first.is_ok
    assert second.is_ok

    await _CreateTwoUsersHandler(SqlIdentityUnitOfWork(db_session)).execute(
        first.value, second.value
    )

    db_session.expunge_all()
    users = list((await db_session.scalars(select(UserModel))).all())
    outbox = list((await db_session.scalars(select(OutboxMessage))).all())
    assert {user.email for user in users} == {"first@example.com", "second@example.com"}
    assert [row.event_type for row in outbox] == [
        "user.registered.v1",
        "user.registered.v1",
    ]

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserAuditAction, UserAuditLog, UserRole
from app.repository import UserAuditLogRepository, UserRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_user(session: AsyncSession, username: str) -> User:
    return await UserRepository(session).create(
        username=username, password_hash="hashed-password"
    )


async def _audit_logs(session: AsyncSession, user_id: int) -> list[UserAuditLog]:
    result = await session.scalars(
        select(UserAuditLog)
        .where(UserAuditLog.user_id == user_id)
        .order_by(UserAuditLog.created_at)
    )
    return list(result.all())


async def test_create_persists_a_user_with_default_role_and_active_state(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "ivanov")

    assert user.id is not None
    assert user.username == "ivanov"
    assert user.password_hash == "hashed-password"
    assert user.role == UserRole.USER
    assert user.is_active is True


async def test_create_writes_a_registered_audit_log(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "petrov")

    log = await db_session.scalar(
        select(UserAuditLog).where(UserAuditLog.user_id == user.id)
    )

    assert log is not None
    assert log.action == UserAuditAction.REGISTERED
    # Вне HTTP-запроса current_actor_id не выставлен, поэтому актором
    # считается сам зарегистрировавшийся пользователь (см. app/audit.py).
    assert log.actor_user_id == user.id


async def test_get_user_by_name_finds_the_created_user(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "sidorov")
    repository = UserRepository(db_session)

    found = await repository.get_user_by_name("sidorov")

    assert found is not None
    assert found.id == user.id


async def test_get_user_by_name_returns_none_for_an_unknown_username(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    assert await repository.get_user_by_name("no-such-user") is None


async def test_get_user_by_id_finds_the_created_user(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "kuznecov")
    repository = UserRepository(db_session)

    found = await repository.get_user_by_id(user.id)

    assert found is not None
    assert found.username == "kuznecov"


async def test_get_user_by_id_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    assert await repository.get_user_by_id(999_999) is None


async def test_update_user_password_changes_the_hash(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "morozov")
    repository = UserRepository(db_session)

    updated = await repository.update_user_password(user.id, "new-hashed-password")

    assert updated is not None
    assert updated.password_hash == "new-hashed-password"


async def test_update_user_password_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    assert await repository.update_user_password(999_999, "irrelevant") is None


async def test_update_user_password_writes_a_password_changed_audit_log(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "volkov")
    repository = UserRepository(db_session)

    await repository.update_user_password(user.id, "new-hashed-password")

    logs = await _audit_logs(db_session, user.id)
    assert [log.action for log in logs] == [
        UserAuditAction.REGISTERED,
        UserAuditAction.PASSWORD_CHANGED,
    ]
    assert logs[-1].actor_user_id == user.id


async def test_set_active_user_deactivates_and_reactivates(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "lebedev")
    repository = UserRepository(db_session)

    deactivated = await repository.set_active_user(user.id, False)
    assert deactivated is not None
    assert deactivated.is_active is False

    reactivated = await repository.set_active_user(user.id, True)
    assert reactivated is not None
    assert reactivated.is_active is True


async def test_set_active_user_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    assert await repository.set_active_user(999_999, False) is None


async def test_deactivate_then_activate_writes_matching_audit_logs(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "kozlov")
    repository = UserRepository(db_session)

    await repository.set_active_user(user.id, False)
    await repository.set_active_user(user.id, True)

    logs = await _audit_logs(db_session, user.id)
    assert [log.action for log in logs] == [
        UserAuditAction.REGISTERED,
        UserAuditAction.DEACTIVATED,
        UserAuditAction.ACTIVATED,
    ]
    assert all(log.actor_user_id == user.id for log in logs)


async def test_get_audit_logs_by_user_breaks_created_at_ties_by_id(
    db_session: AsyncSession,
) -> None:
    # #29: created_at — server_default=func.now(), которая внутри одной
    # транзакции фиксируется на её старте, а не на момент каждого INSERT, так
    # что несколько audit-строк, вставленных в одной транзакции, могут
    # получить одинаковый created_at. Сортировка обязана добавлять id как
    # tie-breaker, иначе порядок между ними не определён.
    user = await _create_user(db_session, "tie_user")
    # user.id захвачен до commit ниже: expire_on_commit=True в db_session
    # истекает атрибуты user, и повторное обращение к user.id роняет тест
    # с MissingGreenlet вне async-контекста (см. _create_owner в
    # test_product_repository.py).
    user_id = user.id
    tied_created_at = datetime.now()
    tied_logs = [
        UserAuditLog(
            user_id=user_id,
            actor_user_id=user_id,
            action=UserAuditAction.PASSWORD_CHANGED,
            created_at=tied_created_at,
        )
        for _ in range(3)
    ]
    db_session.add_all(tied_logs)
    await db_session.commit()
    for log in tied_logs:
        await db_session.refresh(log)
    repository = UserAuditLogRepository(db_session)

    result = await repository.get_audit_logs_by_user(user_id)

    tied_ids = {log.id for log in tied_logs}
    observed_order = [entry.id for entry in result if entry.id in tied_ids]
    assert observed_order == sorted(tied_ids)

from collections.abc import AsyncIterator
from contextvars import Token

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base
from kernel_platform.pagination import decode_cursor
from observability.context import actor_id_var
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.ports import UserAuditAction
from domain.entities.user import User
from domain.value_objects.email import Email
from infrastructure.db.audit import SqlUserAuditReader
from infrastructure.db.user_repository import SqlUserQueryRepository, UserRepository

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


async def _create_user(repository: UserRepository, email: str) -> User:
    result = User.register(Email.create(email).value, "hashed-password")
    assert result.is_ok
    await repository.add(result.value)
    return result.value


async def test_user_query_repository_lists_users_with_cursor_pagination(
    db_session: AsyncSession, _schema: None
) -> None:
    repository = UserRepository(db_session)
    users = [
        await _create_user(repository, "first-read@example.com"),
        await _create_user(repository, "second-read@example.com"),
        await _create_user(repository, "third-read@example.com"),
    ]
    query_repository = SqlUserQueryRepository(db_session)

    first_page = await query_repository.list(limit=2)
    assert len(first_page.items) == 2
    assert first_page.page_info.has_more is True
    assert first_page.page_info.next_cursor is not None
    assert all(item.email.value != "hashed-password" for item in first_page.items)

    second_page = await query_repository.list(
        limit=2, after=decode_cursor(first_page.page_info.next_cursor)
    )

    assert len(second_page.items) == 1
    assert second_page.page_info.has_more is False
    assert {item.id.value for item in first_page.items + second_page.items} == {
        user.id.value for user in users
    }


async def test_user_audit_reader_supports_global_offset_and_personal_modes(
    db_session: AsyncSession, _schema: None
) -> None:
    repository = UserRepository(db_session)
    actor = await _create_user(repository, "read-actor@example.com")
    target = await _create_user(repository, "read-target@example.com")
    loaded_target = await repository.get_by_id(target.id)
    assert loaded_target is not None
    loaded_target.pull_events()

    token: Token[int | str | None] = actor_id_var.set(str(actor.id.value))
    try:
        assert loaded_target.deactivate().is_ok
        await repository.save(loaded_target)
    finally:
        actor_id_var.reset(token)

    reader = SqlUserAuditReader(db_session)
    own_entries = await reader.get_by_user(actor.id)
    target_entries = await reader.get_by_user(target.id)
    global_page = await reader.list_all(page_index=1, page_size=2)

    assert [entry.action for entry in own_entries] == [UserAuditAction.REGISTERED]
    assert [entry.action for entry in target_entries] == [
        UserAuditAction.REGISTERED,
        UserAuditAction.DEACTIVATED,
    ]
    assert global_page.page_index == 1
    assert global_page.page_size == 2
    assert global_page.total == 3
    assert global_page.total_pages == 2
    assert len(global_page.items) == 2

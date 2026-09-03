from datetime import datetime, timezone

from kernel_platform.pagination import Cursor, PageInfo

from application.ports import (
    UserAuditAction,
    UserAuditEntry,
    UserAuditPage,
    UserPage,
    UserReadModel,
)
from application.queries.get_user_audit import (
    GetUserAuditQuery,
    GetUserAuditQueryHandler,
)
from application.queries.list_users import ListUsersQuery, ListUsersQueryHandler
from domain.email import Email
from domain.role import Role
from domain.user_id import UserId

_UserAuditEntries = list[UserAuditEntry]


class FakeUserReadRepository:
    def __init__(self) -> None:
        self.users = UserPage(
            items=[
                UserReadModel(
                    id=UserId.generate(),
                    email=Email("admin@example.com"),
                    role=Role.ADMIN,
                    is_active=True,
                )
            ],
            page_info=PageInfo("next", "previous", True, True),
        )
        self.list_call: tuple[int, Cursor | None, Cursor | None] | None = None
        self.audit_page = UserAuditPage(
            items=[], page_index=2, page_size=10, total=11, total_pages=2
        )
        self.audit_entries = [
            UserAuditEntry(
                id=1,
                user_id=UserId.generate(),
                actor_user_id=UserId.generate(),
                action=UserAuditAction.REGISTERED,
                description="Зарегистрирован пользователь",
                created_at=datetime.now(timezone.utc),
            )
        ]
        self.audit_list_call: tuple[int, int] | None = None
        self.audit_user_call: UserId | None = None

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None:
        return next((item for item in self.users.items if item.id == user_id), None)

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> UserPage:
        self.list_call = (limit, after, before)
        return self.users

    async def list_all(self, *, page_index: int, page_size: int) -> UserAuditPage:
        self.audit_list_call = (page_index, page_size)
        return self.audit_page

    async def get_by_user(self, user_id: UserId) -> _UserAuditEntries:
        self.audit_user_call = user_id
        return self.audit_entries


async def test_list_users_query_returns_cursor_page_from_read_repository() -> None:
    repository = FakeUserReadRepository()
    after = Cursor(datetime(2026, 1, 1, tzinfo=timezone.utc), UserId.generate().value)

    result = await ListUsersQueryHandler(repository).execute(
        ListUsersQuery(limit=5, after=after)
    )

    assert result is repository.users
    assert repository.list_call == (5, after, None)


async def test_user_audit_query_returns_global_offset_page() -> None:
    repository = FakeUserReadRepository()

    result = await GetUserAuditQueryHandler(repository, repository).execute(
        GetUserAuditQuery(page_index=2, page_size=10)
    )

    assert result.is_ok
    assert result.value is repository.audit_page
    assert repository.audit_list_call == (2, 10)
    assert repository.audit_user_call is None


async def test_user_audit_query_reads_personal_audit_without_pagination() -> None:
    repository = FakeUserReadRepository()
    user_id = repository.users.items[0].id

    result = await GetUserAuditQueryHandler(repository, repository).execute(
        GetUserAuditQuery(user_id=user_id)
    )

    assert result.is_ok
    assert result.value is repository.audit_entries
    assert repository.audit_user_call == user_id
    assert repository.audit_list_call is None


async def test_user_audit_query_returns_not_found_for_an_unknown_target_user() -> None:
    repository = FakeUserReadRepository()

    result = await GetUserAuditQueryHandler(repository, repository).execute(
        GetUserAuditQuery(user_id=UserId.generate())
    )

    assert result.is_err
    assert result.error.code == "user_not_found"
    assert repository.audit_user_call is None

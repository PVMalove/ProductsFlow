from kernel_platform.outbox.drain import drain_events_to_outbox
from kernel_platform.pagination import Cursor, PageInfo, encode_cursor
from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports import UserListQueryPort, UserPage, UserReadModel
from domain.email import Email
from domain.repositories import UserRepository as UserRepositoryPort
from domain.role import Role
from domain.user import User
from domain.user_id import UserId

# Importing the listener module is intentional: it registers User ORM events
# whenever the repository is used, including from application code.
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db.models import UserModel

_UserRows = list[UserModel]


def _to_domain(row: UserModel) -> User:
    return User(
        UserId(row.id),
        email=Email(row.email),
        password_hash=row.password_hash,
        role=Role(row.role),
        is_active=row.is_active,
    )


class UserRepository:
    """Async adapter that is the only boundary seeing both User and the DB."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_by_email(self, email: Email) -> bool:
        return bool(
            await self.session.scalar(
                select(UserModel.id).where(UserModel.email == email.value)
            )
        )

    async def get_by_email(self, email: Email) -> User | None:
        row = await self.session.scalar(
            select(UserModel).where(UserModel.email == email.value)
        )
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, user_id: UserId) -> User | None:
        row = await self.session.get(UserModel, user_id.value)
        return _to_domain(row) if row is not None else None

    async def add(self, user: User) -> None:
        self.session.add(_to_model(user))
        await self._commit(user)

    async def save(self, user: User) -> None:
        row = await self.session.get(UserModel, user.id.value)
        if row is None:
            return
        row.email = user.email.value
        row.password_hash = user.password_hash
        row.role = user.role.value
        row.is_active = user.is_active
        await self._commit(user)

    async def _commit(self, user: User) -> None:
        await drain_events_to_outbox(self.session, user)
        await self.session.commit()


def _to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id.value,
        email=user.email.value,
        password_hash=user.password_hash,
        role=user.role.value,
        is_active=user.is_active,
    )


_user_repository_implementation: type[UserRepositoryPort] = UserRepository


def _to_read_model(row: UserModel) -> UserReadModel:
    return UserReadModel(
        id=UserId(row.id),
        email=Email(row.email),
        role=Role(row.role),
        is_active=row.is_active,
    )


class SqlUserQueryRepository:
    """Read-only SQL adapter for the identity application's query port."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None:
        row = await self.session.get(UserModel, user_id.value)
        return _to_read_model(row) if row is not None else None

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> UserPage:
        base_stmt = select(UserModel)
        if before is not None:
            stmt = base_stmt.where(
                tuple_(UserModel.created_at, UserModel.id)
                > (before.created_at, before.id)
            ).order_by(UserModel.created_at.asc(), UserModel.id.asc())
            rows, has_prev = await self._overfetch(stmt, limit)
            rows.reverse()
            has_more = True
        else:
            stmt = base_stmt
            if after is not None:
                stmt = stmt.where(
                    tuple_(UserModel.created_at, UserModel.id)
                    < (after.created_at, after.id)
                )
            stmt = stmt.order_by(UserModel.created_at.desc(), UserModel.id.desc())
            rows, has_more = await self._overfetch(stmt, limit)
            has_prev = after is not None

        if not rows:
            return UserPage(
                items=[],
                page_info=PageInfo(
                    next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
                ),
            )

        return UserPage(
            items=[_to_read_model(row) for row in rows],
            page_info=PageInfo(
                next_cursor=(
                    encode_cursor(rows[-1].created_at, rows[-1].id)
                    if has_more
                    else None
                ),
                prev_cursor=(
                    encode_cursor(rows[0].created_at, rows[0].id) if has_prev else None
                ),
                has_more=has_more,
                has_prev=has_prev,
            ),
        )

    async def _overfetch(
        self, stmt: Select[tuple[UserModel]], limit: int
    ) -> tuple[_UserRows, bool]:
        rows: _UserRows = list(
            (await self.session.scalars(stmt.limit(limit + 1))).all()
        )
        return rows[:limit], len(rows) > limit


_user_list_query_port_implementation: type[UserListQueryPort] = SqlUserQueryRepository

from kernel_platform.outbox.drain import drain_events_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.email import Email
from domain.repositories import UserRepository as UserRepositoryPort
from domain.role import Role
from domain.user import User
from domain.user_id import UserId

# Importing the listener module is intentional: it registers User ORM events
# whenever the repository is used, including from application code.
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db.models import UserModel


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

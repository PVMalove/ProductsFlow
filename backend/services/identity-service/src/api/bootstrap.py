import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from application.commands import (
    ChangeUserRoleCommand,
    ChangeUserRoleCommandHandler,
    RegisterUserCommand,
    RegisterUserCommandHandler,
)
from core.settings import settings
from domain.email import Email
from domain.role import Role
from domain.user_id import UserId
from infrastructure.db.unit_of_work import SqlIdentityUnitOfWork
from infrastructure.security.password_hasher import BcryptPasswordHasher

logger = logging.getLogger(__name__)


async def seed_admin_user(
    engine: AsyncEngine, *, admin_email: str, admin_password: str
) -> None:
    """Ensure exactly one admin user exists, through real command handlers
    (ADR 0017, issue #207) — no direct repository writes for identity/role.

    Idempotent: a user already at `role=ADMIN` for `admin_email` is a no-op.
    A user that exists but isn't ADMIN yet (a prior partial run) is promoted
    without re-registering, since email uniqueness would reject that.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        uow = SqlIdentityUnitOfWork(session)
        email = Email(admin_email)

        existing = await uow.users.get_by_email(email)
        if existing is not None and existing.role == Role.ADMIN:
            logger.info("identity-bootstrap: admin user already seeded; skipping")
            return

        if existing is None:
            register_result = await RegisterUserCommandHandler(
                uow, BcryptPasswordHasher()
            ).execute(RegisterUserCommand(admin_email, admin_password))
            if register_result.is_err:
                raise RuntimeError(
                    f"identity-bootstrap: failed to register admin user: "
                    f"{register_result.error.description}"
                )
            target_user_id = UserId(register_result.value.id)
        else:
            target_user_id = existing.id

        change_role_result = await ChangeUserRoleCommandHandler(uow).execute(
            ChangeUserRoleCommand(target_user_id=target_user_id, role=Role.ADMIN)
        )
        if change_role_result.is_err:
            raise RuntimeError(
                f"identity-bootstrap: failed to promote admin user: "
                f"{change_role_result.error.description}"
            )
    logger.info("identity-bootstrap: admin user seeded")


async def main() -> None:
    if not settings.identity_database_url:
        raise RuntimeError("IDENTITY_DATABASE_URL must be configured")
    if not settings.admin_email:
        raise RuntimeError("ADMIN_EMAIL must be configured")
    if not settings.admin_password:
        raise RuntimeError("ADMIN_PASSWORD must be configured")

    engine = create_async_engine(settings.identity_database_url)
    try:
        await seed_admin_user(
            engine,
            admin_email=settings.admin_email,
            admin_password=settings.admin_password,
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

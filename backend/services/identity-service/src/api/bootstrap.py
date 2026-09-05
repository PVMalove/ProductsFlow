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
from domain.role import Role
from domain.value_objects.email import Email
from domain.value_objects.user_id import UserId
from infrastructure.db.unit_of_work import SqlIdentityUnitOfWork
from infrastructure.security.password_hasher import BcryptPasswordHasher

logger = logging.getLogger(__name__)


async def seed_admin_user(
    engine: AsyncEngine, *, admin_email: str, admin_password: str
) -> None:
    """Гарантирует существование ровно одного admin-пользователя через
    настоящие command handlers (ADR 0001, issue #207) — без прямых записей
    в репозиторий identity/role.

    Идемпотентно: пользователь, уже имеющий `role=ADMIN` для `admin_email`,
    — no-op. Пользователь, который существует, но ещё не ADMIN (предыдущий
    частичный прогон), промоутится без повторной регистрации, поскольку
    уникальность email её бы отклонила.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        uow = SqlIdentityUnitOfWork(session)
        email_result = Email.create(admin_email)
        if email_result.is_err:
            raise RuntimeError(
                f"identity-bootstrap: invalid admin email: "
                f"{email_result.error.description}"
            )
        email = email_result.value

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
            target_user_id = UserId.create(register_result.value.id)
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

    engine = create_async_engine(
        settings.identity_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    import os

    if os.environ.get("SKIP_SEED") == "true":
        logger.info("identity-bootstrap: seed skipped due to SKIP_SEED=true")
        return

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

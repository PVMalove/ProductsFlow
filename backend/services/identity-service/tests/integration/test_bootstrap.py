from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base, OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from api.bootstrap import seed_admin_user
from domain.role import Role
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db import models as _models  # noqa: F401
from infrastructure.db.models import UserModel

pytestmark = pytest.mark.asyncio(loop_scope="session")

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "super-secret-password1"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


async def test_seed_admin_user_is_idempotent_on_a_clean_database(
    db_engine: AsyncEngine, _schema: None
) -> None:
    await seed_admin_user(
        db_engine, admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD
    )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        users = list((await session.scalars(select(UserModel))).all())
        assert len(users) == 1
        assert users[0].email == ADMIN_EMAIL
        assert users[0].role == Role.ADMIN.value

        outbox_rows = list(
            (
                await session.scalars(select(OutboxMessage).order_by(OutboxMessage.id))
            ).all()
        )
        assert [row.event_type for row in outbox_rows] == [
            "user.registered.v1",
            "user.role_changed.v1",
        ]

    await seed_admin_user(
        db_engine, admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD
    )

    async with session_factory() as session:
        users = list((await session.scalars(select(UserModel))).all())
        assert len(users) == 1

        outbox_rows = list((await session.scalars(select(OutboxMessage))).all())
        assert len(outbox_rows) == 2

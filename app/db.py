from collections.abc import AsyncIterator
from typing import Annotated, Any

from alembic.config import Config
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command
from app.models import Product, User, UserRole
from app.settings import settings

engine: AsyncEngine = create_async_engine(settings.database_url, echo=True)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def _run_upgrade(connection: Connection) -> None:
    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def run_migrations() -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_run_upgrade)


async def seed_db() -> None:
    async with SessionLocal() as session, session.begin():
        admin = await _ensure_admin_seeded(session)
        await _ensure_products_seeded(session, owner_id=admin.id)


async def _ensure_admin_seeded(session: AsyncSession) -> User:
    from app.security import hash_password

    """Возвращает существующего или создаёт нового seed-админа."""
    existing = await session.scalar(
        select(User).where(User.username == _SEED_ADMIN["username"])
    )
    if existing is not None:
        return existing

    admin = User(
        username=_SEED_ADMIN["username"],
        password_hash=hash_password(settings.admin_password),
        role=_SEED_ADMIN["role"],
    )
    session.add(admin)
    await session.flush()
    return admin


async def _ensure_products_seeded(session: AsyncSession, owner_id: int) -> None:
    result = await session.execute(select(func.count()).select_from(Product))
    count = result.scalar_one()
    if count > 0:
        return

    products = [
        Product(**product_data, user_id=owner_id) for product_data in _SEED_PRODUCTS
    ]
    session.add_all(products)


_SEED_PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Ноутбук",
        "category": "Электроника",
        "price": 89990.0,
        "description": "Лёгкий ноутбук для работы и учёбы",
    },
    {
        "name": "Смартфон",
        "category": "Электроника",
        "price": 54990.0,
        "description": "Смартфон с хорошей камерой",
    },
    {
        "name": "Кофеварка",
        "category": "Бытовая техника",
        "price": 12990.0,
        "description": "Капельная кофеварка для дома",
    },
    {
        "name": "Чайник",
        "category": "Бытовая техника",
        "price": 2990.0,
        "description": "Электрический чайник, объём 1.7 л",
    },
    {
        "name": "Книга по Python",
        "category": "Книги",
        "price": 1490.0,
        "description": "Введение в язык программирования Python",
    },
    {
        "name": "Книга по FastAPI",
        "category": "Книги",
        "price": 1990.0,
        "description": "Практическое руководство по фреймворку FastAPI",
    },
]


_SEED_ADMIN: dict[str, Any] = {
    "username": "admin",
    "role": UserRole.ADMIN,
}

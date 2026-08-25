import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
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
from app.models import Product, ProductImage, User, UserRole
from app.seed_factories import generate_products
from app.settings import settings
from app.storage import get_storage

SEED_PLACEHOLDER_KEY = "seed/placeholder.jpg"
SEED_PLACEHOLDER_PATH = Path(__file__).parent / "assets" / "placeholder.jpg"

engine: AsyncEngine = create_async_engine(
    settings.database_url, echo=settings.app_env.lower() == "dev"
)
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
        admin: User = await _ensure_admin_seeded(session)
        await _ensure_products_seeded(session, owner_id=admin.id)


async def _ensure_admin_seeded(session: AsyncSession) -> User:
    """Возвращает существующего или создаёт нового seed-админа."""
    from app.security import hash_password

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


async def _ensure_products_seeded(session: "AsyncSession", owner_id: int) -> None:
    # Оптимизация SQLAlchemy: использование scalar()
    count = await session.scalar(select(func.count()).select_from(Product))
    if count and count > 0:
        return

    # Асинхронное чтение файла (защита от блокировки event loop)
    placeholder_bytes = await asyncio.to_thread(SEED_PLACEHOLDER_PATH.read_bytes)

    # Загружаем картинку в S3 через класс S3Storage
    storage = get_storage()
    await storage.ensure_object_exists(
        bucket_name=settings.minio_bucket_name_product,  # Не забудьте передать бакет
        key=SEED_PLACEHOLDER_KEY,
        body=placeholder_bytes,
        content_type="image/jpeg",
    )

    # Генерация продуктов
    products = [
        Product(**product_data, user_id=owner_id)
        for product_data in generate_products(360)
    ]
    session.add_all(products)

    await session.flush()

    # Создаем изображения продуктов
    size_bytes = len(placeholder_bytes)
    images = [
        ProductImage(
            product_id=p.id,
            s3_key=SEED_PLACEHOLDER_KEY,
            content_type="image/jpeg",
            size_bytes=size_bytes,
        )
        for p in products
    ]
    session.add_all(images)

    await session.commit()


_SEED_ADMIN: dict[str, Any] = {
    "username": "admin",
    "role": UserRole.ADMIN,
}

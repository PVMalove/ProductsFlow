import asyncio
import logging
import time
import uuid
from pathlib import Path

import httpx
from kernel_platform.security import ActorRole
from kernel_platform.security.identity_client import IdentityClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.seed_factories import generate_products
from application.commands import (
    CreateProductCommand,
    CreateProductCommandHandler,
    UpsertProductImageCommand,
    UpsertProductImageCommandHandler,
)
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerReadModel,
    ProductImageStorage,
)
from core.settings import settings
from infrastructure.db.entity_configurations.models import ProductModel
from infrastructure.db.owner_read_model import SqlOwnerReadModel
from infrastructure.db.unit_of_work import SqlCatalogUnitOfWork
from infrastructure.identity_gateway import IdentityGatewayAdapter
from infrastructure.storage import ensure_minio_buckets, get_storage

logger = logging.getLogger(__name__)

ADMIN_ROLE = ActorRole.ADMIN.value
PRODUCT_COUNT = 360
ADMIN_DISCOVERY_TIMEOUT_SECONDS = 120.0
ADMIN_DISCOVERY_POLL_INTERVAL_SECONDS = 2.0
PLACEHOLDER_CONTENT_TYPE = "image/jpeg"


async def wait_for_admin_user_id(
    read_model: OwnerReadModel,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> uuid.UUID:
    """Ограниченный по времени поллинг строки `OwnerReadModel`, которую
    `catalog-worker` проецирует из событий identity
    `user.registered.v1`/`user.role_changed.v1` (issue #208) — фиксированного
    или заранее известного admin id не существует (`users.id` — UUID),
    поэтому это единственный способ его обнаружить. Падает громко, а не
    выдумывает `user_id`, если строка так и не появилась."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        snapshot = await read_model.find_by_role(ADMIN_ROLE)
        if snapshot is not None:
            return snapshot.user_id
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "catalog-bootstrap: no OwnerReadModel row with role="
                f"{ADMIN_ROLE!r} appeared within {timeout_seconds}s"
            )
        await asyncio.sleep(poll_interval_seconds)


def _load_placeholder_image() -> bytes:
    return Path(settings.catalog_seed_placeholder_image_path).read_bytes()


async def _seed_products(
    session: AsyncSession,
    *,
    admin_user_id: uuid.UUID,
    identity: IdentityGateway,
    image_storage: ProductImageStorage,
    bucket_name: str,
) -> None:
    """Создаёт `PRODUCT_COUNT` демо-товаров через настоящие хендлеры
    `CreateProductCommand`/`UpsertProductImageCommand` (issue #208) — без
    прямых записей в репозиторий доменных сущностей, которыми они владеют.
    Идемпотентно: непустая таблица `products` означает, что предыдущий
    запуск уже засеял каталог, поэтому это no-op."""
    existing_count = await session.scalar(
        select(func.count()).select_from(ProductModel)
    )
    if existing_count:
        logger.info("catalog-bootstrap: products already seeded; skipping")
        return

    uow = SqlCatalogUnitOfWork(session)
    create_handler = CreateProductCommandHandler(
        uow, SqlOwnerReadModel(session), identity
    )
    image_handler = UpsertProductImageCommandHandler(
        uow, identity, image_storage, bucket_name
    )
    actor = Actor(user_id=admin_user_id, token="")
    placeholder_bytes = await asyncio.to_thread(_load_placeholder_image)

    for product_seed in generate_products(PRODUCT_COUNT):
        result = await create_handler.execute(
            CreateProductCommand(
                actor=actor,
                name=product_seed.name,
                description=product_seed.description,
                price=product_seed.price,
                category=product_seed.category,
            )
        )
        if result.is_err:
            raise RuntimeError(
                f"catalog-bootstrap: failed to seed product {product_seed.name!r}: "
                f"{result.error.description}"
            )
        product = result.value
        await image_handler.execute(
            UpsertProductImageCommand(
                product_id=product.id,
                actor=actor,
                body=placeholder_bytes,
                content_type=PLACEHOLDER_CONTENT_TYPE,
            )
        )

    logger.info("catalog-bootstrap: seeded %s demo products", PRODUCT_COUNT)


async def seed_catalog_demo_data(
    engine: AsyncEngine,
    *,
    identity: IdentityGateway,
    image_storage: ProductImageStorage,
    bucket_name: str,
    admin_discovery_timeout_seconds: float = ADMIN_DISCOVERY_TIMEOUT_SECONDS,
    admin_discovery_poll_interval_seconds: float = (
        ADMIN_DISCOVERY_POLL_INTERVAL_SECONDS
    ),
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        admin_user_id = await wait_for_admin_user_id(
            SqlOwnerReadModel(session),
            timeout_seconds=admin_discovery_timeout_seconds,
            poll_interval_seconds=admin_discovery_poll_interval_seconds,
        )
        await _seed_products(
            session,
            admin_user_id=admin_user_id,
            identity=identity,
            image_storage=image_storage,
            bucket_name=bucket_name,
        )


async def main() -> None:
    if not settings.catalog_database_url:
        raise RuntimeError("CATALOG_DATABASE_URL must be configured")

    await ensure_minio_buckets()

    engine = create_async_engine(settings.catalog_database_url)
    http_client = httpx.AsyncClient(base_url=settings.catalog_identity_base_url)
    identity = IdentityGatewayAdapter(IdentityClient(http_client))
    try:
        await seed_catalog_demo_data(
            engine,
            identity=identity,
            image_storage=get_storage(),
            bucket_name=settings.minio_bucket_name_product,
        )
    finally:
        await http_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from api.bootstrap import seed_catalog_demo_data
from infrastructure.db.entity_configurations.models import (
    ProductImageModel,
    ProductModel,
)
from infrastructure.db.owner_read_model import (
    OwnerReadModelRow,
    upsert_owner_read_model,
)
from infrastructure.identity_gateway import IdentityGatewayAdapter
from tests.integration.conftest import FakeImageStorage
from tests.integration.fake_identity_gateway import FakeIdentityGateway

pytestmark = pytest.mark.asyncio(loop_scope="session")

ADMIN_ID = uuid.uuid4()
BUCKET_NAME = "product-chunks"


@pytest_asyncio.fixture(loop_scope="session")
async def _clean_catalog_tables(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """`seed_catalog_demo_data` commits through its own engine-bound session
    (not the savepoint-rollback `db_session` fixture), so this test's writes
    must be cleaned up explicitly to avoid leaking 360 products into the
    shared session-scoped schema other integration tests run against."""
    try:
        yield
    finally:
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with session_factory() as session:
            await session.execute(delete(ProductImageModel))
            await session.execute(delete(ProductModel))
            await session.execute(delete(OwnerReadModelRow))
            await session.commit()


async def _seed_admin_owner_row(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await upsert_owner_read_model(
            session,
            user_id=ADMIN_ID,
            role="admin",
            is_active=True,
            last_applied_outbox_id=1,
        )


async def test_seed_catalog_demo_data_creates_360_owned_imaged_products(
    db_engine: AsyncEngine, _clean_catalog_tables: None
) -> None:
    """Issue #208 AC: a full seed run, against a database where the admin's
    events have already been projected into OwnerReadModel, produces 360
    correctly-owned, imaged products."""
    await _seed_admin_owner_row(db_engine)
    image_storage = FakeImageStorage()

    await seed_catalog_demo_data(
        db_engine,
        identity=IdentityGatewayAdapter(FakeIdentityGateway()),
        image_storage=image_storage,
        bucket_name=BUCKET_NAME,
        admin_discovery_timeout_seconds=1.0,
        admin_discovery_poll_interval_seconds=0.01,
    )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        products = list((await session.scalars(select(ProductModel))).all())
        assert len(products) == 360
        assert all(product.user_id == ADMIN_ID for product in products)

        image_count = await session.scalar(
            select(func.count()).select_from(ProductImageModel)
        )
        assert image_count == 360

    assert len(image_storage.objects) == 360


async def test_seed_catalog_demo_data_is_idempotent(
    db_engine: AsyncEngine, _clean_catalog_tables: None
) -> None:
    await _seed_admin_owner_row(db_engine)
    image_storage = FakeImageStorage()

    for _ in range(2):
        await seed_catalog_demo_data(
            db_engine,
            identity=IdentityGatewayAdapter(FakeIdentityGateway()),
            image_storage=image_storage,
            bucket_name=BUCKET_NAME,
            admin_discovery_timeout_seconds=1.0,
            admin_discovery_poll_interval_seconds=0.01,
        )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        product_count = await session.scalar(
            select(func.count()).select_from(ProductModel)
        )
        assert product_count == 360

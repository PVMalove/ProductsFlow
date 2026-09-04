"""Transactional integration seam for catalog command-side mutations (issue #246)."""

import uuid

import pytest
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.product_id import ProductId
from infrastructure.db.audit import ProductAuditLog
from infrastructure.db.models import ProductImageModel, ProductModel
from infrastructure.db.unit_of_work import SqlCatalogUnitOfWork

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_image_mutations_rollback_together_without_partial_audit_or_outbox(
    db_session: AsyncSession,
) -> None:
    """A failure after an image write leaves neither image nor audit/outbox state."""
    owner_id = uuid.uuid4()
    product_id = uuid.uuid4()
    db_session.add(
        ProductModel(
            id=product_id,
            name="Товар",
            description="",
            price=1.0,
            category="Категория",
            user_id=owner_id,
        )
    )
    await db_session.commit()

    uow = SqlCatalogUnitOfWork(db_session)
    with pytest.raises(RuntimeError, match="storage failed"):
        async with uow:
            await uow.products.upsert_product_image(
                ProductId(product_id),
                s3_key=f"products/{product_id}/image",
                content_type="image/jpeg",
                size_bytes=10,
                actor_user_id=owner_id,
            )
            raise RuntimeError("storage failed")

    db_session.expunge_all()
    assert (
        await db_session.scalar(
            select(ProductImageModel).where(ProductImageModel.product_id == product_id)
        )
        is None
    )
    audits = list(
        (
            await db_session.scalars(
                select(ProductAuditLog)
                .where(ProductAuditLog.product_id == product_id)
                .order_by(ProductAuditLog.id)
            )
        ).all()
    )
    assert [audit.action for audit in audits] == ["created"]
    assert (
        await db_session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == product_id)
        )
        is None
    )


async def test_image_mutation_commits_its_audit_without_creating_outbox_message(
    db_session: AsyncSession,
) -> None:
    owner_id = uuid.uuid4()
    product_id = uuid.uuid4()
    db_session.add(
        ProductModel(
            id=product_id,
            name="Товар",
            description="",
            price=1.0,
            category="Категория",
            user_id=owner_id,
        )
    )
    await db_session.commit()

    uow = SqlCatalogUnitOfWork(db_session)
    async with uow:
        await uow.products.upsert_product_image(
            ProductId(product_id),
            s3_key=f"products/{product_id}/image",
            content_type="image/jpeg",
            size_bytes=10,
            actor_user_id=owner_id,
        )
        await uow.commit()

    assert (
        await db_session.scalar(
            select(ProductImageModel).where(ProductImageModel.product_id == product_id)
        )
        is not None
    )
    audits = list(
        (
            await db_session.scalars(
                select(ProductAuditLog)
                .where(ProductAuditLog.product_id == product_id)
                .order_by(ProductAuditLog.id)
            )
        ).all()
    )
    assert [audit.action for audit in audits] == ["created", "image_updated"]
    assert (
        await db_session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == product_id)
        )
        is None
    )

"""Transactional integration seam for catalog command-side mutations (issue #246)."""

import uuid

import pytest
from kernel_platform.outbox.models import OutboxMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import CreateProductCommand, CreateProductCommandHandler
from application.ports import Actor, IdentityUser
from domain.product_id import ProductId
from infrastructure.db.audit import ProductAuditLog
from infrastructure.db.models import ProductImageModel, ProductModel
from infrastructure.db.owner_read_model import OwnerReadModelRow, SqlOwnerReadModel
from infrastructure.db.unit_of_work import SqlCatalogUnitOfWork

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _IdentityGateway:
    def __init__(self, user_id: uuid.UUID) -> None:
        self._user_id = user_id

    async def fetch_current_user(self, token: str) -> IdentityUser:
        return IdentityUser(id=self._user_id, role="user", is_active=True)


async def test_failed_create_rolls_back_cold_start_owner_projection(
    db_session: AsyncSession,
) -> None:
    """The separately injected OwnerReadModel shares the handler's UoW."""
    owner_id = uuid.uuid4()
    handler = CreateProductCommandHandler(
        SqlCatalogUnitOfWork(db_session),
        SqlOwnerReadModel(db_session),
        _IdentityGateway(owner_id),
    )

    result = await handler.execute(
        CreateProductCommand(
            actor=Actor(user_id=owner_id, token="token"),
            name="ab",
            description="",
            price=1.0,
            category="Категория",
        )
    )

    assert result.is_err
    assert await db_session.get(OwnerReadModelRow, owner_id) is None


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

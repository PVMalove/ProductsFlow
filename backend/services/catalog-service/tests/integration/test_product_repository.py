import uuid
from datetime import datetime

import pytest
from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.pagination import decode_cursor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.value_objects.product_id import ProductId
from infrastructure.db.audit import ProductAuditLog
from infrastructure.db.entity_configurations.models import ProductModel
from infrastructure.db.owner_read_model import upsert_owner_read_model
from infrastructure.db.product_repository import ProductRepository
from infrastructure.db.unit_of_work import SqlCatalogUnitOfWork

pytestmark = pytest.mark.asyncio(loop_scope="session")

UNKNOWN_PRODUCT_ID = ProductId.create(uuid.uuid4())
PAGINATION_PRODUCT_IDS = (
    uuid.UUID("00000000-0000-0000-0000-000000000001"),
    uuid.UUID("00000000-0000-0000-0000-000000000002"),
    uuid.UUID("00000000-0000-0000-0000-000000000003"),
)


async def _seed_pagination_products(session: AsyncSession, owner_id: uuid.UUID) -> None:
    created_at = datetime(2026, 8, 30, 12, 0, 0)
    session.add_all(
        [
            ProductModel(
                id=product_id,
                name=f"Товар {product_id}",
                category="Категория",
                price=1.0,
                description="",
                user_id=owner_id,
                created_at=created_at,
            )
            for product_id in PAGINATION_PRODUCT_IDS
        ]
    )
    await session.commit()


async def _outbox_rows_for(
    session: AsyncSession, aggregate_id: uuid.UUID
) -> list[OutboxMessage]:
    rows = await session.scalars(
        select(OutboxMessage)
        .where(OutboxMessage.aggregate_id == aggregate_id)
        .order_by(OutboxMessage.id)
    )
    return list(rows.all())


async def _audit_rows_for(
    session: AsyncSession, product_id: uuid.UUID
) -> list[ProductAuditLog]:
    rows = await session.scalars(
        select(ProductAuditLog)
        .where(ProductAuditLog.product_id == product_id)
        .order_by(ProductAuditLog.id)
    )
    return list(rows.all())


async def test_create_persists_product_and_writes_outbox_row_in_same_transaction(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    owner_id = uuid.uuid4()

    result = await repo.create(
        name="Название товара",
        description="Описание",
        price=9.99,
        category="Категория",
        user_id=owner_id,
    )

    assert result.is_ok
    product = result.value

    fetched = await repo.get_by_id(product.id)
    assert fetched is not None
    assert fetched.name == "Название товара"
    assert fetched.user_id == owner_id

    outbox_rows = await _outbox_rows_for(db_session, product.id.value)
    assert len(outbox_rows) == 1
    assert outbox_rows[0].event_type == "product.created.v1"
    assert outbox_rows[0].payload["user_id"] == str(owner_id)

    audit_rows = await _audit_rows_for(db_session, product.id.value)
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "created"


async def test_create_rejects_invalid_product_without_persisting(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)

    result = await repo.create(
        name="ab",
        description="",
        price=1.0,
        category="Категория",
        user_id=uuid.uuid4(),
    )

    assert result.is_err
    assert result.error.code == "invalid_name"


async def test_get_by_id_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    repo = ProductRepository(db_session)

    assert await repo.get_by_id(UNKNOWN_PRODUCT_ID) is None


async def test_update_applies_only_provided_fields_and_writes_outbox_row(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    created = (
        await repo.create(
            name="Исходное имя",
            description="Описание",
            price=5.0,
            category="Категория",
            user_id=uuid.uuid4(),
        )
    ).value

    result = await repo.update(created.id, name="Новое имя")

    assert result is not None
    assert result.is_ok
    updated = result.value
    assert updated.name == "Новое имя"
    assert updated.category == "Категория"

    outbox_rows = await _outbox_rows_for(db_session, created.id.value)
    assert [row.event_type for row in outbox_rows] == [
        "product.created.v1",
        "product.updated.v1",
    ]


async def test_update_unknown_product_returns_none(db_session: AsyncSession) -> None:
    repo = ProductRepository(db_session)

    assert await repo.update(UNKNOWN_PRODUCT_ID, name="x") is None


async def test_activate_deactivate_toggle_persisted_state(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    created = (
        await repo.create(
            name="Название товара",
            description="",
            price=1.0,
            category="Категория",
            user_id=uuid.uuid4(),
        )
    ).value

    deactivated = await repo.deactivate(created.id)
    assert deactivated is not None and deactivated.is_ok
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.is_active is False

    activated = await repo.activate(created.id)
    assert activated is not None and activated.is_ok
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.is_active is True

    outbox_rows = await _outbox_rows_for(db_session, created.id.value)
    assert [row.event_type for row in outbox_rows] == [
        "product.created.v1",
        "product.deactivated.v1",
        "product.activated.v1",
    ]


async def test_delete_removes_row_and_writes_outbox_row(
    db_session: AsyncSession,
) -> None:
    uow = SqlCatalogUnitOfWork(db_session)
    async with uow:
        created = (
            await uow.products.create(
                name="Название товара",
                description="",
                price=1.0,
                category="Категория",
                user_id=uuid.uuid4(),
            )
        ).value

        deleted = await uow.products.delete(created.id)
        assert deleted is not None
        await uow.commit()

    assert await uow.products.get_by_id(created.id) is None

    outbox_rows = await _outbox_rows_for(db_session, created.id.value)
    assert [row.event_type for row in outbox_rows] == [
        "product.created.v1",
        "product.deleted.v1",
    ]

    audit_rows = await _audit_rows_for(db_session, created.id.value)
    assert [row.action for row in audit_rows] == ["created", "deleted"]


async def test_delete_unknown_product_returns_none(db_session: AsyncSession) -> None:
    repo = ProductRepository(db_session)

    assert await repo.delete(UNKNOWN_PRODUCT_ID) is None


async def test_list_paginates_with_keyset_cursor(db_session: AsyncSession) -> None:
    repo = ProductRepository(db_session)
    owner_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=owner_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=1,
    )
    await _seed_pagination_products(db_session, owner_id)

    first_page = await repo.list(limit=2)
    first_page_ids = [p.id.value for p in first_page.items]
    assert first_page_ids == list(reversed(PAGINATION_PRODUCT_IDS[1:]))
    assert first_page.page_info.has_more is True
    assert first_page.page_info.next_cursor is not None

    second_page = await repo.list(
        limit=2, after=decode_cursor(first_page.page_info.next_cursor)
    )
    second_page_ids = [p.id.value for p in second_page.items]
    assert second_page_ids == [PAGINATION_PRODUCT_IDS[0]]
    assert second_page.page_info.has_more is False


async def test_list_before_cursor_navigates_back_to_a_newer_page(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    owner_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=owner_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=1,
    )
    await _seed_pagination_products(db_session, owner_id)

    first_page = await repo.list(limit=2)
    assert first_page.page_info.next_cursor is not None
    second_page = await repo.list(
        limit=2, after=decode_cursor(first_page.page_info.next_cursor)
    )
    assert second_page.page_info.prev_cursor is not None

    page_before = await repo.list(
        limit=2, before=decode_cursor(second_page.page_info.prev_cursor)
    )

    assert [p.id.value for p in page_before.items] == list(
        reversed(PAGINATION_PRODUCT_IDS[1:])
    )
    assert page_before.page_info.has_more is True


async def test_list_hides_deactivated_products_from_everyone(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    owner_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=owner_id,
        role="user",
        is_active=True,
        last_applied_outbox_id=1,
    )
    active = (
        await repo.create(
            name="Активный",
            description="",
            price=1.0,
            category="Категория",
            user_id=owner_id,
        )
    ).value
    inactive = (
        await repo.create(
            name="Неактивный",
            description="",
            price=1.0,
            category="Категория",
            user_id=owner_id,
        )
    ).value
    await repo.deactivate(inactive.id)

    page = await repo.list(limit=10)

    assert [p.id.value for p in page.items] == [active.id.value]


async def test_list_hides_products_of_a_deactivated_owner(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    owner_id = uuid.uuid4()
    await upsert_owner_read_model(
        db_session,
        user_id=owner_id,
        role="user",
        is_active=False,
        last_applied_outbox_id=1,
    )
    await repo.create(
        name="Товар деактивированного владельца",
        description="",
        price=1.0,
        category="Категория",
        user_id=owner_id,
    )

    page = await repo.list(limit=10)

    assert page.items == []


async def test_list_hides_products_of_an_unknown_owner(
    db_session: AsyncSession,
) -> None:
    """Строка ещё не появилась в owner_read_model (ни событием, ни
    синхронным добором) — осторожный дефолт: скрыт, а не показан."""
    repo = ProductRepository(db_session)
    await repo.create(
        name="Товар без owner_read_model",
        description="",
        price=1.0,
        category="Категория",
        user_id=uuid.uuid4(),
    )

    page = await repo.list(limit=10)

    assert page.items == []


async def test_upsert_product_image_replaces_the_single_row_and_audits_it(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    actor_id = uuid.uuid4()
    product = (
        await repo.create(
            name="Картинка товара",
            description="",
            price=1.0,
            category="Категория",
            user_id=actor_id,
        )
    ).value

    first = await repo.upsert_product_image(
        product.id,
        s3_key=f"products/{product.id.value}/image",
        content_type="image/jpeg",
        size_bytes=10,
        actor_user_id=actor_id,
    )
    second = await repo.upsert_product_image(
        product.id,
        s3_key=f"products/{product.id.value}/image",
        content_type="image/png",
        size_bytes=20,
        actor_user_id=actor_id,
    )

    assert first.product_id == product.id
    assert second.product_id == product.id
    assert second.content_type == "image/png"
    assert second.size_bytes == 20

    stored = await repo.get_product_image(product.id)
    assert stored == second

    rows = await db_session.scalars(
        select(ProductAuditLog)
        .where(ProductAuditLog.product_id == product.id.value)
        .order_by(ProductAuditLog.id)
    )
    assert [row.action for row in rows.all()] == [
        "created",
        "image_updated",
        "image_updated",
    ]


async def test_delete_product_image_removes_row_and_writes_explicit_audit(
    db_session: AsyncSession,
) -> None:
    repo = ProductRepository(db_session)
    actor_id = uuid.uuid4()
    product = (
        await repo.create(
            name="Картинка товара",
            description="",
            price=1.0,
            category="Категория",
            user_id=actor_id,
        )
    ).value
    await repo.upsert_product_image(
        product.id,
        s3_key=f"products/{product.id.value}/image",
        content_type="image/jpeg",
        size_bytes=10,
        actor_user_id=actor_id,
    )

    await repo.delete_product_image(product.id, actor_user_id=actor_id)

    assert await repo.get_product_image(product.id) is None
    rows = await db_session.scalars(
        select(ProductAuditLog)
        .where(ProductAuditLog.product_id == product.id.value)
        .order_by(ProductAuditLog.id)
    )
    assert [row.action for row in rows.all()] == [
        "created",
        "image_updated",
        "image_deleted",
    ]

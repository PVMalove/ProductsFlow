import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductAuditAction, ProductAuditLog, User
from app.repository import ProductRepository
from app.schemas import ProductCreate, ProductResponse, ProductUpdate

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_owner(session: AsyncSession, username: str = "owner") -> int:
    user = User(username=username, password_hash="hashed-password")
    session.add(user)
    await session.flush()
    return user.id


async def _create_product(
    session: AsyncSession,
    owner_id: int,
    name: str = "Ноутбук",
    category: str = "Электроника",
    price: float = 1000.0,
    description: str = "",
) -> ProductResponse:
    request = ProductCreate(
        name=name, category=category, price=price, description=description
    )
    return await ProductRepository(session).create_product(request, owner_id)


async def _audit_logs(session: AsyncSession, product_id: int) -> list[ProductAuditLog]:
    result = await session.scalars(
        select(ProductAuditLog)
        .where(ProductAuditLog.product_id == product_id)
        .order_by(ProductAuditLog.created_at)
    )
    return list(result.all())


async def test_create_product_persists_and_returns_the_created_product(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)

    product = await _create_product(db_session, owner_id, name="Ноутбук")

    assert product.id is not None
    assert product.name == "Ноутбук"
    assert product.category == "Электроника"
    assert product.price == 1000.0
    assert product.user_id == owner_id


async def test_create_product_writes_a_created_audit_log(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)

    product = await _create_product(db_session, owner_id)

    logs = await _audit_logs(db_session, product.id)
    assert len(logs) == 1
    assert logs[0].action == ProductAuditAction.CREATED
    # Вне HTTP-запроса current_actor_id не выставлен, поэтому актором
    # считается владелец продукта (см. app/audit.py::_resolve_product_actor).
    assert logs[0].actor_user_id == owner_id


async def test_get_product_by_id_finds_the_created_product(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    found = await repository.get_product_by_id(product.id)

    assert found is not None
    assert found.id == product.id


async def test_get_product_by_id_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = ProductRepository(db_session)

    assert await repository.get_product_by_id(999_999) is None


async def test_get_all_products_returns_every_product(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Ноутбук")
    await _create_product(db_session, owner_id, name="Смартфон")
    repository = ProductRepository(db_session)

    products = await repository.get_all_products()

    assert {product.name for product in products} == {"Ноутбук", "Смартфон"}


async def test_search_products_matches_the_name_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    # Пустое описание намеренно: непустое дефолтное описание могло бы
    # случайно содержать искомую подстроку и замаскировать баг в name.
    await _create_product(db_session, owner_id, name="Ноутбук")
    repository = ProductRepository(db_session)

    lower = await repository.search_products("ноутбук")
    upper = await repository.search_products("НОУТБУК")

    assert [product.name for product in lower] == ["Ноутбук"]
    assert [product.name for product in upper] == ["Ноутбук"]


async def test_search_products_matches_the_description_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(
        db_session, owner_id, name="Чайник", description="Электрический чайник"
    )
    repository = ProductRepository(db_session)

    found = await repository.search_products("ЭЛЕКТРИЧЕСКИЙ")

    assert [product.name for product in found] == ["Чайник"]


async def test_search_products_does_not_match_unrelated_products(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Ноутбук")
    repository = ProductRepository(db_session)

    assert await repository.search_products("холодильник") == []


async def test_get_products_by_category_matches_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, category="Электроника")
    repository = ProductRepository(db_session)

    lower = await repository.get_products_by_category("электроника")
    upper = await repository.get_products_by_category("ЭЛЕКТРОНИКА")

    assert len(lower) == 1
    assert len(upper) == 1


async def test_get_products_by_category_does_not_match_a_different_category(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, category="Электроника")
    repository = ProductRepository(db_session)

    assert await repository.get_products_by_category("Книги") == []


async def test_get_products_by_price_range_filters_by_both_bounds(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Средний", price=500.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range(200.0, 800.0)

    assert [product.name for product in found] == ["Средний"]


async def test_get_products_by_price_range_with_only_min_price(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range(500.0, None)

    assert [product.name for product in found] == ["Дорогой"]


async def test_get_products_by_price_range_with_only_max_price(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range(None, 500.0)

    assert [product.name for product in found] == ["Дешёвый"]


async def test_update_product_changes_only_the_given_fields(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id, name="Ноутбук", price=1000.0)
    repository = ProductRepository(db_session)

    updated = await repository.update_product(product.id, ProductUpdate(price=1200.0))

    assert updated is not None
    assert updated.price == 1200.0
    assert updated.name == "Ноутбук"


async def test_update_product_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = ProductRepository(db_session)

    result = await repository.update_product(999_999, ProductUpdate(price=1.0))

    assert result is None


async def test_update_product_writes_an_updated_audit_log(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    await repository.update_product(product.id, ProductUpdate(price=1200.0))

    logs = await _audit_logs(db_session, product.id)
    assert [log.action for log in logs] == [
        ProductAuditAction.CREATED,
        ProductAuditAction.UPDATED,
    ]
    assert logs[-1].actor_user_id == owner_id


async def test_delete_product_removes_the_product_and_returns_a_snapshot(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id, name="Ноутбук")
    repository = ProductRepository(db_session)

    deleted = await repository.delete_product(product.id)

    assert deleted is not None
    assert deleted.name == "Ноутбук"
    assert await db_session.get(Product, product.id) is None


async def test_delete_product_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = ProductRepository(db_session)

    assert await repository.delete_product(999_999) is None


async def test_delete_product_writes_a_deleted_audit_log_that_survives_the_product(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    await repository.delete_product(product.id)

    logs = await _audit_logs(db_session, product.id)
    assert [log.action for log in logs] == [
        ProductAuditAction.CREATED,
        ProductAuditAction.DELETED,
    ]
    assert logs[-1].actor_user_id == owner_id

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductAuditAction, ProductAuditLog, User
from app.pagination import Cursor, decode_cursor
from app.repository import ProductRepository
from app.schemas import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_owner(session: AsyncSession, username: str = "owner") -> int:
    # Возвращаем голый id, а не User: большинство вызовов ProductRepository
    # ниже сами делают session.commit(), после чего атрибуты owner истекают
    # (expire_on_commit=True в фикстуре db_session) и повторное обращение
    # к owner.id роняет тест с MissingGreenlet вне async-контекста.
    user = User(username=username, password_hash="hashed-password")
    session.add(user)
    await session.flush()
    return user.id


async def _deactivate_owner(session: AsyncSession, owner_id: int) -> None:
    owner = await session.get(User, owner_id)
    assert owner is not None
    owner.is_active = False
    await session.commit()


def _cursor_of(raw: str | None) -> Cursor:
    assert raw is not None
    return decode_cursor(raw)


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


async def test_get_product_by_id_finds_an_active_owners_product_for_non_admin_viewer(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    product = await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    found = await repository.get_product_by_id(product.id, viewer_is_admin=False)

    assert found is not None
    assert found.id == product.id


async def test_get_product_by_id_hides_a_deactivated_owners_product_from_non_admin(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session, username="id_inactive_owner")
    product = await _create_product(db_session, owner_id)
    await _deactivate_owner(db_session, owner_id)
    repository = ProductRepository(db_session)

    found = await repository.get_product_by_id(product.id, viewer_is_admin=False)

    assert found is None


async def test_get_product_by_id_shows_a_deactivated_owners_product_to_admin_viewer(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session, username="id_inactive_owner2")
    product = await _create_product(db_session, owner_id)
    await _deactivate_owner(db_session, owner_id)
    repository = ProductRepository(db_session)

    found = await repository.get_product_by_id(product.id, viewer_is_admin=True)

    assert found is not None
    assert found.id == product.id


async def test_get_products_page_orders_newest_first(db_session: AsyncSession) -> None:
    owner_id = await _create_owner(db_session)
    first = await _create_product(db_session, owner_id, name="Первый")
    second = await _create_product(db_session, owner_id, name="Второй")
    third = await _create_product(db_session, owner_id, name="Третий")
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.id for product in page.items] == [third.id, second.id, first.id]


async def test_get_products_page_first_page_reports_no_previous_page(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id)
    await _create_product(db_session, owner_id)
    await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )

    assert len(page.items) == 2
    assert page.page_info.has_prev is False
    assert page.page_info.prev_cursor is None


async def test_get_products_page_reports_a_next_cursor_when_more_rows_exist(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id)
    await _create_product(db_session, owner_id)
    await _create_product(db_session, owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )

    assert page.page_info.has_more is True
    assert page.page_info.next_cursor is not None
    last_item = page.items[-1]
    cursor = _cursor_of(page.page_info.next_cursor)
    assert cursor.created_at == last_item.created_at
    assert cursor.id == last_item.id


async def test_get_products_page_after_cursor_returns_the_remaining_rows(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    first = await _create_product(db_session, owner_id, name="Первый")
    await _create_product(db_session, owner_id, name="Второй")
    await _create_product(db_session, owner_id, name="Третий")
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )
    assert first_page.page_info.next_cursor is not None

    second_page = await repository.get_products_page(
        limit=2,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    assert [product.id for product in second_page.items] == [first.id]
    assert second_page.page_info.has_more is False
    assert second_page.page_info.next_cursor is None
    assert second_page.page_info.has_prev is True
    assert second_page.page_info.prev_cursor is not None


async def test_get_products_page_before_cursor_returns_the_previous_page(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    p1 = await _create_product(db_session, owner_id, name="Товар1")
    p2 = await _create_product(db_session, owner_id, name="Товар2")
    p3 = await _create_product(db_session, owner_id, name="Товар3")
    p4 = await _create_product(db_session, owner_id, name="Товар4")
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [p4.id, p3.id]

    second_page = await repository.get_products_page(
        limit=2,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )
    assert [product.id for product in second_page.items] == [p2.id, p1.id]

    back_to_first_page = await repository.get_products_page(
        limit=2,
        after=None,
        before=_cursor_of(second_page.page_info.prev_cursor),
        viewer_is_admin=False,
    )

    assert [product.id for product in back_to_first_page.items] == [p4.id, p3.id]
    assert back_to_first_page.page_info.has_prev is False
    assert back_to_first_page.page_info.prev_cursor is None
    assert back_to_first_page.page_info.has_more is True


async def test_get_products_page_is_unaffected_by_deleting_an_already_delivered_row(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    p1 = await _create_product(db_session, owner_id, name="Товар1")
    p2 = await _create_product(db_session, owner_id, name="Товар2")
    p3 = await _create_product(db_session, owner_id, name="Товар3")
    p4 = await _create_product(db_session, owner_id, name="Товар4")
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [p4.id, p3.id]

    await repository.delete_product(p3.id)

    second_page = await repository.get_products_page(
        limit=2,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    # p3 уже отдан на первой странице — его удаление не влияет на вторую.
    assert [product.id for product in second_page.items] == [p2.id, p1.id]
    assert second_page.page_info.has_more is False


async def test_get_products_page_skips_a_row_deleted_before_it_was_delivered(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    p1 = await _create_product(db_session, owner_id, name="Товар1")
    p2 = await _create_product(db_session, owner_id, name="Товар2")
    p3 = await _create_product(db_session, owner_id, name="Товар3")
    p4 = await _create_product(db_session, owner_id, name="Товар4")
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_page(
        limit=2, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [p4.id, p3.id]

    await repository.delete_product(p2.id)

    second_page = await repository.get_products_page(
        limit=2,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    assert [product.id for product in second_page.items] == [p1.id]


async def test_get_products_page_hides_products_of_deactivated_owners_by_default(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="active_owner")
    inactive_owner_id = await _create_owner(db_session, username="inactive_owner")
    visible = await _create_product(db_session, active_owner_id, name="Видимый")
    await _create_product(db_session, inactive_owner_id, name="Скрытый")
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.id for product in page.items] == [visible.id]


async def test_get_products_page_admin_sees_products_of_deactivated_owners(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="active_owner2")
    inactive_owner_id = await _create_owner(db_session, username="inactive_owner2")
    visible = await _create_product(db_session, active_owner_id, name="Видимый")
    hidden = await _create_product(db_session, inactive_owner_id, name="Скрытый")
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=10, after=None, before=None, viewer_is_admin=True
    )

    assert {product.id for product in page.items} == {visible.id, hidden.id}


async def test_get_products_page_returns_an_empty_page_when_there_are_no_products(
    db_session: AsyncSession,
) -> None:
    repository = ProductRepository(db_session)

    page = await repository.get_products_page(
        limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert page == ProductListResponse.model_validate(
        {
            "items": [],
            "page_info": {
                "next_cursor": None,
                "prev_cursor": None,
                "has_more": False,
                "has_prev": False,
            },
        }
    )


async def test_search_products_page_matches_the_name_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    # Пустое описание намеренно: непустое дефолтное описание могло бы
    # случайно содержать искомую подстроку и замаскировать баг в name.
    await _create_product(db_session, owner_id, name="Ноутбук")
    repository = ProductRepository(db_session)

    lower = await repository.search_products_page(
        "ноутбук", limit=10, after=None, before=None, viewer_is_admin=False
    )
    upper = await repository.search_products_page(
        "НОУТБУК", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.name for product in lower.items] == ["Ноутбук"]
    assert [product.name for product in upper.items] == ["Ноутбук"]


async def test_search_products_page_matches_the_description_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(
        db_session, owner_id, name="Чайник", description="Электрический чайник"
    )
    repository = ProductRepository(db_session)

    found = await repository.search_products_page(
        "ЭЛЕКТРИЧЕСКИЙ", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.name for product in found.items] == ["Чайник"]


async def test_search_products_page_does_not_match_unrelated_products(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Ноутбук")
    repository = ProductRepository(db_session)

    found = await repository.search_products_page(
        "холодильник", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert found.items == []


async def test_search_products_page_after_cursor_returns_the_remaining_matching_rows(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    first = await _create_product(db_session, owner_id, name="Ноутбук Первый")
    await _create_product(db_session, owner_id, name="Холодильник")
    second = await _create_product(db_session, owner_id, name="Ноутбук Второй")
    third = await _create_product(db_session, owner_id, name="Ноутбук Третий")
    repository = ProductRepository(db_session)

    first_page = await repository.search_products_page(
        "Ноутбук", limit=2, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [third.id, second.id]

    second_page = await repository.search_products_page(
        "Ноутбук",
        limit=2,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    # "Холодильник" не подходит под query — не должен просочиться на вторую
    # страницу курсорной навигации, хотя и стоит между двумя "Ноутбук" по
    # created_at.
    assert [product.id for product in second_page.items] == [first.id]
    assert second_page.page_info.has_more is False


async def test_search_products_page_hides_matches_of_deactivated_owners_by_default(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="search_active_owner")
    inactive_owner_id = await _create_owner(
        db_session, username="search_inactive_owner"
    )
    visible = await _create_product(db_session, active_owner_id, name="Ноутбук Актив")
    await _create_product(db_session, inactive_owner_id, name="Ноутбук Скрытый")
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.search_products_page(
        "Ноутбук", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.id for product in page.items] == [visible.id]


async def test_search_products_page_admin_sees_matches_of_deactivated_owners(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="search_active_owner2")
    inactive_owner_id = await _create_owner(
        db_session, username="search_inactive_owner2"
    )
    visible = await _create_product(db_session, active_owner_id, name="Ноутбук Актив")
    hidden = await _create_product(
        db_session, inactive_owner_id, name="Ноутбук Скрытый"
    )
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.search_products_page(
        "Ноутбук", limit=10, after=None, before=None, viewer_is_admin=True
    )

    assert {product.id for product in page.items} == {visible.id, hidden.id}


async def test_get_products_by_category_page_matches_regardless_of_case(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, category="Электроника")
    repository = ProductRepository(db_session)

    lower = await repository.get_products_by_category_page(
        "электроника", limit=10, after=None, before=None, viewer_is_admin=False
    )
    upper = await repository.get_products_by_category_page(
        "ЭЛЕКТРОНИКА", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert len(lower.items) == 1
    assert len(upper.items) == 1


async def test_get_products_by_category_page_does_not_match_a_different_category(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, category="Электроника")
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_category_page(
        "Книги", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert found.items == []


async def test_get_products_by_category_page_after_cursor_stays_within_category(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    a = await _create_product(
        db_session, owner_id, name="Товар А", category="Электроника"
    )
    await _create_product(db_session, owner_id, name="Товар Чужой", category="Книги")
    b = await _create_product(
        db_session, owner_id, name="Товар Б", category="Электроника"
    )
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_by_category_page(
        "Электроника", limit=1, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [b.id]

    second_page = await repository.get_products_by_category_page(
        "Электроника",
        limit=1,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    # "Товар Чужой" из другой категории — не должен просочиться на вторую
    # страницу курсорной навигации, хотя и стоит между А и Б по created_at.
    assert [product.id for product in second_page.items] == [a.id]
    assert second_page.page_info.has_more is False


async def test_category_page_hides_matches_of_deactivated_owners_by_default(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="cat_active_owner")
    inactive_owner_id = await _create_owner(db_session, username="cat_inactive_owner")
    visible = await _create_product(
        db_session, active_owner_id, name="Видимый", category="Электроника"
    )
    await _create_product(
        db_session, inactive_owner_id, name="Скрытый", category="Электроника"
    )
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_by_category_page(
        "Электроника", limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.id for product in page.items] == [visible.id]


async def test_category_page_admin_sees_matches_of_deactivated_owners(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="cat_active_owner2")
    inactive_owner_id = await _create_owner(db_session, username="cat_inactive_owner2")
    visible = await _create_product(
        db_session, active_owner_id, name="Видимый", category="Электроника"
    )
    hidden = await _create_product(
        db_session, inactive_owner_id, name="Скрытый", category="Электроника"
    )
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_by_category_page(
        "Электроника", limit=10, after=None, before=None, viewer_is_admin=True
    )

    assert {product.id for product in page.items} == {visible.id, hidden.id}


async def test_get_products_by_price_range_page_filters_by_both_bounds(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Средний", price=500.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range_page(
        200.0, 800.0, limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.name for product in found.items] == ["Средний"]


async def test_get_products_by_price_range_page_with_only_min_price(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range_page(
        500.0, None, limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.name for product in found.items] == ["Дорогой"]


async def test_get_products_by_price_range_page_with_only_max_price(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    await _create_product(db_session, owner_id, name="Дешёвый", price=100.0)
    await _create_product(db_session, owner_id, name="Дорогой", price=900.0)
    repository = ProductRepository(db_session)

    found = await repository.get_products_by_price_range_page(
        None, 500.0, limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.name for product in found.items] == ["Дешёвый"]


async def test_get_products_by_price_range_page_after_cursor_stays_within_bounds(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_owner(db_session)
    a = await _create_product(db_session, owner_id, name="Товар А", price=200.0)
    await _create_product(db_session, owner_id, name="Товар Дорогой", price=900.0)
    b = await _create_product(db_session, owner_id, name="Товар Б", price=300.0)
    repository = ProductRepository(db_session)

    first_page = await repository.get_products_by_price_range_page(
        100.0, 500.0, limit=1, after=None, before=None, viewer_is_admin=False
    )
    assert [product.id for product in first_page.items] == [b.id]

    second_page = await repository.get_products_by_price_range_page(
        100.0,
        500.0,
        limit=1,
        after=_cursor_of(first_page.page_info.next_cursor),
        before=None,
        viewer_is_admin=False,
    )

    # "Товар Дорогой" вне диапазона — не должен просочиться на вторую
    # страницу курсорной навигации, хотя и стоит между А и Б по created_at.
    assert [product.id for product in second_page.items] == [a.id]
    assert second_page.page_info.has_more is False


async def test_price_range_page_hides_matches_of_deactivated_owners_by_default(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="price_active_owner")
    inactive_owner_id = await _create_owner(db_session, username="price_inactive_owner")
    visible = await _create_product(
        db_session, active_owner_id, name="Видимый", price=500.0
    )
    await _create_product(db_session, inactive_owner_id, name="Скрытый", price=500.0)
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_by_price_range_page(
        None, None, limit=10, after=None, before=None, viewer_is_admin=False
    )

    assert [product.id for product in page.items] == [visible.id]


async def test_price_range_page_admin_sees_matches_of_deactivated_owners(
    db_session: AsyncSession,
) -> None:
    active_owner_id = await _create_owner(db_session, username="price_active_owner2")
    inactive_owner_id = await _create_owner(
        db_session, username="price_inactive_owner2"
    )
    visible = await _create_product(
        db_session, active_owner_id, name="Видимый", price=500.0
    )
    hidden = await _create_product(
        db_session, inactive_owner_id, name="Скрытый", price=500.0
    )
    await _deactivate_owner(db_session, inactive_owner_id)
    repository = ProductRepository(db_session)

    page = await repository.get_products_by_price_range_page(
        None, None, limit=10, after=None, before=None, viewer_is_admin=True
    )

    assert {product.id for product in page.items} == {visible.id, hidden.id}


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

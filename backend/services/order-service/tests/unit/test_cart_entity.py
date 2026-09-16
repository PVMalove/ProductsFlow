"""Domain-агрегат Cart (архитектурный бриф issue #369, Seams for TDD #1) —
Always-Valid Domain: количество проверяется в самом агрегате, повторное
добавление того же товара мержится (D4), мутации над неизвестной строкой
отклоняются доменной ошибкой `line_not_found` (D7)."""

import uuid
from datetime import UTC, datetime

from domain.entities.cart import Cart
from domain.value_objects.cart_id import CartId

USER_ID = uuid.uuid4()


def _new_cart() -> Cart:
    return Cart.create(CartId.new_id(), user_id=USER_ID)


def test_create_starts_with_no_lines() -> None:
    cart = _new_cart()

    assert cart.user_id == USER_ID
    assert cart.lines == []


def test_add_line_rejects_non_positive_quantity() -> None:
    cart = _new_cart()

    result = cart.add_line(
        line_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        quantity=0,
        now=datetime.now(UTC),
    )

    assert result.is_err
    assert result.error.code == "invalid_quantity"
    assert cart.lines == []


def test_add_line_creates_a_new_line() -> None:
    cart = _new_cart()
    product_id = uuid.uuid4()

    result = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=2, now=datetime.now(UTC)
    )

    assert result.is_ok
    assert len(cart.lines) == 1
    assert cart.lines[0].product_id == product_id
    assert cart.lines[0].quantity == 2


def test_add_line_twice_with_same_product_merges_quantity() -> None:
    cart = _new_cart()
    product_id = uuid.uuid4()
    now = datetime.now(UTC)

    first = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=2, now=now
    )
    second = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=3, now=now
    )

    assert first.is_ok
    assert second.is_ok
    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 5
    # D4: та же строка (тот же id), не новая — merge, не отдельная запись.
    assert second.value.id == first.value.id


def test_update_line_quantity_rejects_non_positive_quantity() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id

    result = cart.update_line_quantity(line_id=line_id, quantity=-1)

    assert result.is_err
    assert result.error.code == "invalid_quantity"


def test_update_line_quantity_unknown_line_fails() -> None:
    cart = _new_cart()

    result = cart.update_line_quantity(line_id=uuid.uuid4(), quantity=1)

    assert result.is_err
    assert result.error.code == "line_not_found"


def test_update_line_quantity_updates_existing_line() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id

    result = cart.update_line_quantity(line_id=line_id, quantity=7)

    assert result.is_ok
    assert result.value.quantity == 7
    assert cart.lines[0].quantity == 7


def test_remove_line_unknown_line_fails() -> None:
    cart = _new_cart()

    result = cart.remove_line(line_id=uuid.uuid4())

    assert result.is_err
    assert result.error.code == "line_not_found"


def test_remove_line_removes_existing_line() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id

    result = cart.remove_line(line_id=line_id)

    assert result.is_ok
    assert cart.lines == []


def test_remove_line_twice_fails_the_second_time() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    first = cart.remove_line(line_id=line_id)

    second = cart.remove_line(line_id=line_id)

    assert first.is_ok
    assert second.is_err
    assert second.error.code == "line_not_found"


# --- issue #372, D3: selection-freeze lock-guard ---------------------------


def test_lock_for_checkout_locks_every_line() -> None:
    cart = _new_cart()
    cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=2, now=datetime.now(UTC)
    )
    order_id = uuid.uuid4()

    cart.lock_for_checkout(order_id=order_id)

    assert all(line.locked_by_order_id == order_id for line in cart.lines)


def test_add_line_rejects_merge_into_a_locked_line() -> None:
    cart = _new_cart()
    product_id = uuid.uuid4()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=1, now=datetime.now(UTC)
    )
    cart.lock_for_checkout(order_id=uuid.uuid4())

    result = cart.add_line(
        line_id=uuid.uuid4(), product_id=product_id, quantity=1, now=datetime.now(UTC)
    )

    assert result.is_err
    assert result.error.code == "line_locked"
    assert cart.lines[0].quantity == add_result.value.quantity


def test_update_line_quantity_rejects_a_locked_line() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    cart.lock_for_checkout(order_id=uuid.uuid4())

    result = cart.update_line_quantity(line_id=line_id, quantity=5)

    assert result.is_err
    assert result.error.code == "line_locked"
    assert cart.lines[0].quantity == 1


def test_remove_line_rejects_a_locked_line() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    cart.lock_for_checkout(order_id=uuid.uuid4())

    result = cart.remove_line(line_id=line_id)

    assert result.is_err
    assert result.error.code == "line_locked"
    assert len(cart.lines) == 1


def test_unlock_all_clears_lock_only_for_the_given_order() -> None:
    cart = _new_cart()
    add_result = cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    line_id = add_result.value.id
    order_id = uuid.uuid4()
    cart.lock_for_checkout(order_id=order_id)

    cart.unlock_all(order_id=order_id)

    assert cart.lines[0].locked_by_order_id is None
    assert cart.lines[0].unavailable_reason is None
    # Строка снова мутируема после снятия блокировки.
    result = cart.update_line_quantity(line_id=line_id, quantity=4)
    assert result.is_ok


def test_resolve_partial_reservation_removes_confirmed_and_flags_unavailable() -> None:
    cart = _new_cart()
    confirmed_product_id = uuid.uuid4()
    unavailable_product_id = uuid.uuid4()
    cart.add_line(
        line_id=uuid.uuid4(),
        product_id=confirmed_product_id,
        quantity=1,
        now=datetime.now(UTC),
    )
    cart.add_line(
        line_id=uuid.uuid4(),
        product_id=unavailable_product_id,
        quantity=1,
        now=datetime.now(UTC),
    )
    order_id = uuid.uuid4()
    cart.lock_for_checkout(order_id=order_id)

    cart.resolve_partial_reservation(
        order_id=order_id, confirmed_product_ids=frozenset({confirmed_product_id})
    )

    assert len(cart.lines) == 1
    remaining = cart.lines[0]
    assert remaining.product_id == unavailable_product_id
    assert remaining.locked_by_order_id is None
    assert remaining.unavailable_reason == "insufficient_stock"

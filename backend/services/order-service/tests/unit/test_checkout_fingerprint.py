"""compute_fingerprint (issue #372, D2, Seams for TDD #4) — идемпотентный
fingerprint Checkout Selection: порядок строк не влияет на результат,
изменение состава/количества — влияет."""

import uuid
from datetime import UTC, datetime

from domain.checkout_fingerprint import compute_fingerprint
from domain.entities.cart_line import CartLine


def _line(line_id: uuid.UUID, product_id: uuid.UUID, quantity: int) -> CartLine:
    return CartLine(
        id=line_id, product_id=product_id, quantity=quantity, added_at=datetime.now(UTC)
    )


def test_same_lines_in_different_order_produce_the_same_fingerprint() -> None:
    line_a = _line(uuid.uuid4(), uuid.uuid4(), 2)
    line_b = _line(uuid.uuid4(), uuid.uuid4(), 1)

    forward = compute_fingerprint([line_a, line_b])
    reversed_order = compute_fingerprint([line_b, line_a])

    assert forward == reversed_order


def test_different_quantity_produces_a_different_fingerprint() -> None:
    line_id = uuid.uuid4()
    product_id = uuid.uuid4()

    original = compute_fingerprint([_line(line_id, product_id, 1)])
    changed = compute_fingerprint([_line(line_id, product_id, 2)])

    assert original != changed


def test_different_line_set_produces_a_different_fingerprint() -> None:
    line_id_a = uuid.uuid4()
    line_id_b = uuid.uuid4()
    product_id = uuid.uuid4()

    only_a = compute_fingerprint([_line(line_id_a, product_id, 1)])
    both = compute_fingerprint(
        [_line(line_id_a, product_id, 1), _line(line_id_b, uuid.uuid4(), 1)]
    )

    assert only_a != both


def test_empty_lines_is_stable() -> None:
    assert compute_fingerprint([]) == compute_fingerprint([])

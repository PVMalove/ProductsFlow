"""Domain-агрегат Inventory (ADR 0016, issue #367) — Always-Valid Domain:
неотрицательность остатка проверяется внутри `adjust()`, не только на
API-границе (issue #367, риск 3)."""

import uuid

from domain.entities.inventory import Inventory
from domain.events.inventory_domain_event import InventoryAdjusted


def test_create_zero_starts_at_zero_quantity_with_product_id_as_identity() -> None:
    product_id = uuid.uuid4()

    inventory = Inventory.create_zero(product_id)

    assert inventory.id == product_id
    assert inventory.quantity == 0
    # PK = product_id (брифа находка «Selected option»): создание нулевой
    # записи не публикует собственное доменное событие (Trade-offs брифа).
    assert inventory.pull_events() == []


def test_adjust_increases_quantity_and_records_domain_event() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())

    result = inventory.adjust(5)

    assert result.is_ok
    assert inventory.quantity == 5
    events = inventory.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InventoryAdjusted)
    assert event.event_type == "inventory.adjusted.v1"
    assert event.product_id == inventory.id
    assert event.delta == 5
    assert event.quantity_after == 5


def test_adjust_rejects_negative_result_and_leaves_quantity_unchanged() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    seed = inventory.adjust(5)
    assert seed.is_ok
    inventory.pull_events()

    result = inventory.adjust(-10)

    assert result.is_err
    assert result.error.code == "negative_stock_adjustment"
    assert inventory.quantity == 5
    # Ошибка не должна оставлять "фантомное" событие незакоммиченной попытки.
    assert inventory.pull_events() == []


def test_adjust_allows_result_to_reach_exactly_zero() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    seed = inventory.adjust(3)
    assert seed.is_ok
    inventory.pull_events()

    result = inventory.adjust(-3)

    assert result.is_ok
    assert inventory.quantity == 0


def test_reserve_increases_reserved_when_available_is_sufficient() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    inventory.adjust(10)
    inventory.pull_events()

    result = inventory.reserve(6)

    assert result.is_ok
    assert inventory.reserved == 6
    assert inventory.quantity == 10


def test_reserve_rejects_insufficient_available_and_leaves_reserved_unchanged() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    inventory.adjust(10)
    inventory.pull_events()
    inventory.reserve(4)

    result = inventory.reserve(7)

    assert result.is_err
    assert result.error.code == "insufficient_available_stock"
    assert inventory.reserved == 4


def test_release_decreases_reserved() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    inventory.adjust(10)
    inventory.pull_events()
    inventory.reserve(6)

    result = inventory.release(6)

    assert result.is_ok
    assert inventory.reserved == 0


def test_release_more_than_reserved_is_rejected_as_a_guard() -> None:
    inventory = Inventory.create_zero(uuid.uuid4())
    inventory.adjust(10)
    inventory.pull_events()
    inventory.reserve(3)

    result = inventory.release(4)

    assert result.is_err
    assert result.error.code == "insufficient_available_stock"
    assert inventory.reserved == 3


def test_adjust_rejects_a_delta_that_would_leave_quantity_below_reserved() -> None:
    """Расширенный инвариант (архитектурный бриф, находка 5): admin-корректировка
    не может увести available в минус, даже если итоговый quantity сам по себе
    неотрицателен."""
    inventory = Inventory.create_zero(uuid.uuid4())
    inventory.adjust(10)
    inventory.pull_events()
    inventory.reserve(8)

    result = inventory.adjust(-5)

    assert result.is_err
    assert result.error.code == "negative_stock_adjustment"
    assert inventory.quantity == 10

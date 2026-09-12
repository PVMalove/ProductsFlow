"""application/commands/reserve_inventory_lines.py (issue #370, Seams for
TDD #4) — partial confirm/unavailable across multiple lines; sorted lock
order (D4); try_create() returning False for an existing order_id (D3,
business-layer idempotency) leaves Inventory untouched; a genuine race where
try_create conflicts AFTER partitioning (Risk 6) is compensated."""

import uuid
from datetime import UTC, datetime

from application.commands.reserve_inventory_lines import (
    ReservationLineRequest,
    ReserveInventoryLinesCommand,
    ReserveInventoryLinesCommandHandler,
)
from domain.entities.inventory import Inventory
from domain.entities.reservation import ReservationLineStatus
from domain.reservation_status import ReservationStatus
from tests.unit.fake_inventory_repository import FakeInventoryRepository
from tests.unit.fake_reservation_repository import FakeReservationRepository

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _inventory(product_id: uuid.UUID, quantity: int) -> Inventory:
    inventory = Inventory.create_zero(product_id)
    inventory.adjust(quantity)
    inventory.pull_events()
    return inventory


async def test_execute_partially_confirms_lines_across_multiple_products() -> None:
    plentiful = uuid.uuid4()
    scarce = uuid.uuid4()
    inventory_repo = FakeInventoryRepository(
        [_inventory(plentiful, 10), _inventory(scarce, 1)]
    )
    reservation_repo = FakeReservationRepository()
    handler = ReserveInventoryLinesCommandHandler(
        inventory_repo, reservation_repo, ttl_minutes=15
    )
    order_id = uuid.uuid4()

    await handler.execute(
        ReserveInventoryLinesCommand(
            order_id=order_id,
            lines=(
                ReservationLineRequest(product_id=plentiful, quantity=4),
                ReservationLineRequest(product_id=scarce, quantity=5),
            ),
        ),
        now=NOW,
    )

    reservation = await reservation_repo.get_by_order_id(order_id)
    assert reservation is not None
    assert reservation.status is ReservationStatus.ACTIVE
    by_product = {line.product_id: line for line in reservation.lines}
    assert by_product[plentiful].status is ReservationLineStatus.CONFIRMED
    assert by_product[scarce].status is ReservationLineStatus.UNAVAILABLE
    plentiful_inventory = await inventory_repo.get_by_product_id(plentiful)
    scarce_inventory = await inventory_repo.get_by_product_id(scarce)
    assert plentiful_inventory is not None
    assert scarce_inventory is not None
    assert plentiful_inventory.reserved == 4
    assert scarce_inventory.reserved == 0


async def test_execute_sorts_lines_by_product_id_before_reserving() -> None:
    """D4: детерминированный порядок предотвращает cross-command deadlock."""
    high = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    low = uuid.UUID("00000000-0000-0000-0000-000000000000")
    inventory_repo = FakeInventoryRepository([_inventory(high, 5), _inventory(low, 5)])
    reservation_repo = FakeReservationRepository()
    handler = ReserveInventoryLinesCommandHandler(
        inventory_repo, reservation_repo, ttl_minutes=15
    )

    await handler.execute(
        ReserveInventoryLinesCommand(
            order_id=uuid.uuid4(),
            lines=(
                ReservationLineRequest(product_id=high, quantity=1),
                ReservationLineRequest(product_id=low, quantity=1),
            ),
        ),
        now=NOW,
    )

    assert inventory_repo.reserve_calls == [(low, 1), (high, 1)]


async def test_execute_is_a_business_layer_noop_for_an_existing_order_id() -> None:
    """D3/находка 6, второй слой идемпотентности: другая доставка (другой
    command_id), тот же order_id — не удваивает reserved."""
    product_id = uuid.uuid4()
    inventory = _inventory(product_id, 10)
    inventory_repo = FakeInventoryRepository([inventory])
    order_id = uuid.uuid4()
    command = ReserveInventoryLinesCommand(
        order_id=order_id,
        lines=(ReservationLineRequest(product_id=product_id, quantity=4),),
    )
    reservation_repo = FakeReservationRepository()
    handler = ReserveInventoryLinesCommandHandler(
        inventory_repo, reservation_repo, ttl_minutes=15
    )
    await handler.execute(command, now=NOW)
    assert inventory.reserved == 4

    await handler.execute(command, now=NOW)

    assert inventory.reserved == 4
    assert len(reservation_repo.try_create_calls) == 1


async def test_execute_compensates_reserved_on_a_genuine_try_create_race() -> None:
    """Risk 6: если try_create всё-таки конфликтует ПОСЛЕ партиционирования
    (настоящая гонка двух разных command_id для одного order_id между двумя
    репликами воркера) — reserved не должен остаться навсегда увеличенным
    проигравшей попыткой."""
    product_id = uuid.uuid4()
    inventory = _inventory(product_id, 10)
    inventory_repo = FakeInventoryRepository([inventory])
    reservation_repo = FakeReservationRepository()
    reservation_repo.force_try_create_conflict = True
    handler = ReserveInventoryLinesCommandHandler(
        inventory_repo, reservation_repo, ttl_minutes=15
    )

    await handler.execute(
        ReserveInventoryLinesCommand(
            order_id=uuid.uuid4(),
            lines=(ReservationLineRequest(product_id=product_id, quantity=4),),
        ),
        now=NOW,
    )

    assert inventory.reserved == 0
    assert inventory_repo.release_calls == [(product_id, 4)]

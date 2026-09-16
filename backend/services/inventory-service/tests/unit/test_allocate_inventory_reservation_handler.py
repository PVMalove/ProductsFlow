"""application/commands/allocate_inventory_reservation.py (issue #373, ADR
0016, Seams for TDD #6) — allocate переводит живой резерв ACTIVE -> ALLOCATED
и НЕ трогает `InventoryRepository` вовсе (`Inventory.reserved` уже учитывает
живой резерв независимо от ACTIVE/ALLOCATED, поэтому хендлер зависит только
от `ReservationRepository`, тот же приём доказательства «нет побочного
эффекта на остаток», что структурная форма
`release_inventory_reservation.py`'s handler даёт для release. Аллоцирование
несуществующего/уже неактивного резерва — no-op, не исключение (легитимный
повтор не должен уехать в DLQ)."""

import uuid
from datetime import UTC, datetime

from application.commands.allocate_inventory_reservation import (
    AllocateInventoryReservationCommand,
    AllocateInventoryReservationCommandHandler,
)
from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.reservation_status import ReservationStatus
from tests.unit.fake_reservation_repository import FakeReservationRepository

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _reservation(order_id: uuid.UUID, lines: list[ReservationLine]) -> Reservation:
    reservation = Reservation.create(order_id, lines=lines, ttl_minutes=15, now=NOW)
    reservation.pull_events()
    return reservation


async def test_execute_allocates_active_reservation_and_saves_once() -> None:
    product_id = uuid.uuid4()
    order_id = uuid.uuid4()
    reservation = _reservation(
        order_id,
        [
            ReservationLine(
                id=uuid.uuid4(),
                product_id=product_id,
                quantity=4,
                status=ReservationLineStatus.CONFIRMED,
            )
        ],
    )
    reservation_repo = FakeReservationRepository([reservation])
    handler = AllocateInventoryReservationCommandHandler(reservation_repo)

    await handler.execute(AllocateInventoryReservationCommand(order_id=order_id))

    saved = await reservation_repo.get_by_order_id(order_id)
    assert saved is not None
    assert saved.status is ReservationStatus.ALLOCATED
    assert len(reservation_repo.save_calls) == 1


async def test_execute_is_a_noop_for_an_unknown_order_id() -> None:
    reservation_repo = FakeReservationRepository()
    handler = AllocateInventoryReservationCommandHandler(reservation_repo)

    await handler.execute(AllocateInventoryReservationCommand(order_id=uuid.uuid4()))

    assert reservation_repo.save_calls == []


async def test_execute_is_a_noop_for_an_already_allocated_reservation() -> None:
    order_id = uuid.uuid4()
    reservation = _reservation(
        order_id,
        [
            ReservationLine(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                quantity=4,
                status=ReservationLineStatus.CONFIRMED,
            )
        ],
    )
    reservation.allocate()
    reservation.pull_events()
    reservation_repo = FakeReservationRepository([reservation])
    handler = AllocateInventoryReservationCommandHandler(reservation_repo)

    await handler.execute(AllocateInventoryReservationCommand(order_id=order_id))

    assert reservation_repo.save_calls == []


async def test_execute_is_a_noop_for_a_released_reservation() -> None:
    order_id = uuid.uuid4()
    reservation = _reservation(
        order_id,
        [
            ReservationLine(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                quantity=4,
                status=ReservationLineStatus.CONFIRMED,
            )
        ],
    )
    reservation.release(reason="manual")
    reservation.pull_events()
    reservation_repo = FakeReservationRepository([reservation])
    handler = AllocateInventoryReservationCommandHandler(reservation_repo)

    await handler.execute(AllocateInventoryReservationCommand(order_id=order_id))

    assert reservation_repo.save_calls == []

"""application/commands/release_inventory_reservation.py (issue #370, Seams
for TDD #5) — release restores reserved only for confirmed lines; releasing
a missing/already-inactive reservation is a no-op, not an exception (a
legitimate redelivery must not go to the DLQ)."""

import uuid
from datetime import UTC, datetime

from application.commands.release_inventory_reservation import (
    ReleaseInventoryReservationCommand,
    ReleaseInventoryReservationCommandHandler,
)
from domain.entities.inventory import Inventory
from domain.entities.reservation import Reservation, ReservationLine, ReservationLineStatus
from domain.reservation_status import ReservationStatus
from tests.unit.fake_inventory_repository import FakeInventoryRepository
from tests.unit.fake_reservation_repository import FakeReservationRepository

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _inventory(product_id: uuid.UUID, quantity: int, reserved: int) -> Inventory:
    inventory = Inventory.create_zero(product_id)
    inventory.adjust(quantity)
    inventory.pull_events()
    inventory.reserve(reserved)
    return inventory


def _reservation(order_id: uuid.UUID, lines: list[ReservationLine]) -> Reservation:
    reservation = Reservation.create(order_id, lines=lines, ttl_minutes=15, now=NOW)
    reservation.pull_events()
    return reservation


async def test_execute_releases_confirmed_lines_and_marks_reservation_released() -> None:
    product_id = uuid.uuid4()
    inventory = _inventory(product_id, 10, 4)
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
    inventory_repo = FakeInventoryRepository([inventory])
    reservation_repo = FakeReservationRepository([reservation])
    handler = ReleaseInventoryReservationCommandHandler(inventory_repo, reservation_repo)

    await handler.execute(
        ReleaseInventoryReservationCommand(order_id=order_id, reason="manual")
    )

    assert inventory.reserved == 0
    saved = await reservation_repo.get_by_order_id(order_id)
    assert saved is not None
    assert saved.status is ReservationStatus.RELEASED
    assert len(reservation_repo.save_calls) == 1


async def test_execute_ignores_unavailable_lines_when_restoring_reserved() -> None:
    product_id = uuid.uuid4()
    unavailable_product_id = uuid.uuid4()
    inventory = _inventory(product_id, 10, 4)
    order_id = uuid.uuid4()
    reservation = _reservation(
        order_id,
        [
            ReservationLine(
                id=uuid.uuid4(),
                product_id=product_id,
                quantity=4,
                status=ReservationLineStatus.CONFIRMED,
            ),
            ReservationLine(
                id=uuid.uuid4(),
                product_id=unavailable_product_id,
                quantity=9,
                status=ReservationLineStatus.UNAVAILABLE,
            ),
        ],
    )
    inventory_repo = FakeInventoryRepository([inventory])
    reservation_repo = FakeReservationRepository([reservation])
    handler = ReleaseInventoryReservationCommandHandler(inventory_repo, reservation_repo)

    await handler.execute(
        ReleaseInventoryReservationCommand(order_id=order_id, reason="manual")
    )

    assert inventory_repo.release_calls == [(product_id, 4)]


async def test_execute_is_a_noop_for_an_unknown_order_id() -> None:
    inventory_repo = FakeInventoryRepository()
    reservation_repo = FakeReservationRepository()
    handler = ReleaseInventoryReservationCommandHandler(inventory_repo, reservation_repo)

    await handler.execute(
        ReleaseInventoryReservationCommand(order_id=uuid.uuid4(), reason="manual")
    )

    assert inventory_repo.release_calls == []
    assert reservation_repo.save_calls == []


async def test_execute_is_a_noop_for_an_already_released_reservation() -> None:
    product_id = uuid.uuid4()
    inventory = _inventory(product_id, 10, 4)
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
    reservation.release(reason="manual")
    reservation.pull_events()
    inventory_repo = FakeInventoryRepository([inventory])
    reservation_repo = FakeReservationRepository([reservation])
    handler = ReleaseInventoryReservationCommandHandler(inventory_repo, reservation_repo)

    await handler.execute(
        ReleaseInventoryReservationCommand(order_id=order_id, reason="expired")
    )

    assert inventory_repo.release_calls == []
    assert reservation_repo.save_calls == []

"""Domain-агрегат Reservation (issue #370, ADR 0016, Seams for TDD #3) —
partitioning confirmed/unavailable уже сделан вызывающим (D4/D8): `create()`
просто собирает единственное `InventoryReserved`-событие с корректным
разбиением. `release()` — идемпотентный guard на уровне агрегата (D3/находка
6, второй, business-result слой идемпотентности).

`allocate()`/расширение `release()` — issue #373, ADR 0016 продолжение:
allocate() двигает живой резерв ACTIVE -> ALLOCATED (тот же идемпотентный
guard, только Result.fail без исключения), release() теперь принимает и
ALLOCATED как компенсацию (widened guard), не только ACTIVE."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.events.reservation_domain_event import (
    InventoryAllocated,
    InventoryReleased,
    InventoryReserved,
)
from domain.reservation_status import ReservationStatus

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _line(status: ReservationLineStatus, *, quantity: int = 2) -> ReservationLine:
    return ReservationLine(
        id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=quantity, status=status
    )


def test_create_partitions_confirmed_and_unavailable_into_one_event() -> None:
    order_id = uuid.uuid4()
    confirmed = _line(ReservationLineStatus.CONFIRMED, quantity=3)
    unavailable = _line(ReservationLineStatus.UNAVAILABLE, quantity=5)

    reservation = Reservation.create(
        order_id, lines=[confirmed, unavailable], ttl_minutes=15, now=NOW
    )

    assert reservation.id == order_id
    assert reservation.status is ReservationStatus.ACTIVE
    assert reservation.expires_at == NOW + timedelta(minutes=15)
    events = reservation.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InventoryReserved)
    assert event.event_type == "inventory.reserved.v1"
    assert event.order_id == order_id
    assert event.confirmed_lines == ((confirmed.product_id, 3),)
    assert event.unavailable_lines == ((unavailable.product_id, 5),)


def test_release_from_active_transitions_to_released_keeping_confirmed_lines() -> None:
    confirmed = _line(ReservationLineStatus.CONFIRMED, quantity=4)
    unavailable = _line(ReservationLineStatus.UNAVAILABLE, quantity=1)
    reservation = Reservation.create(
        uuid.uuid4(), lines=[confirmed, unavailable], ttl_minutes=15, now=NOW
    )
    reservation.pull_events()

    result = reservation.release(reason="manual")

    assert result.is_ok
    assert reservation.status is ReservationStatus.RELEASED
    events = reservation.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InventoryReleased)
    assert event.event_type == "inventory.released.v1"
    assert event.reason == "manual"
    assert event.released_lines == ((confirmed.product_id, 4),)


def test_release_twice_is_rejected_as_an_idempotent_guard() -> None:
    reservation = Reservation.create(
        uuid.uuid4(),
        lines=[_line(ReservationLineStatus.CONFIRMED)],
        ttl_minutes=15,
        now=NOW,
    )
    reservation.pull_events()
    first = reservation.release(reason="manual")
    assert first.is_ok
    reservation.pull_events()

    second = reservation.release(reason="expired")

    assert second.is_err
    assert second.error.code == "reservation_not_active"
    assert reservation.status is ReservationStatus.RELEASED
    assert reservation.pull_events() == []


def test_allocate_from_active_transitions_to_allocated_and_emits_event() -> None:
    confirmed = _line(ReservationLineStatus.CONFIRMED, quantity=4)
    unavailable = _line(ReservationLineStatus.UNAVAILABLE, quantity=1)
    reservation = Reservation.create(
        uuid.uuid4(), lines=[confirmed, unavailable], ttl_minutes=15, now=NOW
    )
    reservation.pull_events()

    result = reservation.allocate()

    assert result.is_ok
    assert reservation.status is ReservationStatus.ALLOCATED
    events = reservation.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InventoryAllocated)
    assert event.event_type == "inventory.allocated.v1"
    assert event.order_id == reservation.id
    assert event.allocated_lines == ((confirmed.product_id, 4),)


def test_allocate_twice_is_rejected_as_an_idempotent_guard() -> None:
    reservation = Reservation.create(
        uuid.uuid4(),
        lines=[_line(ReservationLineStatus.CONFIRMED)],
        ttl_minutes=15,
        now=NOW,
    )
    reservation.pull_events()
    first = reservation.allocate()
    assert first.is_ok
    reservation.pull_events()

    second = reservation.allocate()

    assert second.is_err
    assert second.error.code == "reservation_not_active"
    assert reservation.status is ReservationStatus.ALLOCATED
    assert reservation.pull_events() == []


@pytest.mark.parametrize("reason", ["manual", "expired"])
def test_allocate_on_released_or_expired_reservation_is_rejected(
    reason: str,
) -> None:
    reservation = Reservation.create(
        uuid.uuid4(),
        lines=[_line(ReservationLineStatus.CONFIRMED)],
        ttl_minutes=15,
        now=NOW,
    )
    reservation.pull_events()
    reservation.release(reason=reason)  # type: ignore[arg-type]
    reservation.pull_events()

    result = reservation.allocate()

    assert result.is_err
    assert result.error.code == "reservation_not_active"
    assert reservation.pull_events() == []


def test_release_from_allocated_transitions_to_released_keeping_confirmed_lines() -> (
    None
):
    confirmed = _line(ReservationLineStatus.CONFIRMED, quantity=4)
    unavailable = _line(ReservationLineStatus.UNAVAILABLE, quantity=1)
    reservation = Reservation.create(
        uuid.uuid4(), lines=[confirmed, unavailable], ttl_minutes=15, now=NOW
    )
    reservation.pull_events()
    reservation.allocate()
    reservation.pull_events()

    result = reservation.release(reason="manual")

    assert result.is_ok
    assert reservation.status is ReservationStatus.RELEASED
    events = reservation.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InventoryReleased)
    assert event.event_type == "inventory.released.v1"
    assert event.reason == "manual"
    assert event.released_lines == ((confirmed.product_id, 4),)


def test_release_twice_after_allocation_is_rejected_as_idempotent_guard() -> None:
    reservation = Reservation.create(
        uuid.uuid4(),
        lines=[_line(ReservationLineStatus.CONFIRMED)],
        ttl_minutes=15,
        now=NOW,
    )
    reservation.pull_events()
    reservation.allocate()
    reservation.pull_events()
    first = reservation.release(reason="manual")
    assert first.is_ok
    reservation.pull_events()

    second = reservation.release(reason="manual")

    assert second.is_err
    assert second.error.code == "reservation_not_active"
    assert reservation.status is ReservationStatus.RELEASED
    assert reservation.pull_events() == []

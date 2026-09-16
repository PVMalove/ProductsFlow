# ruff: noqa: E501
"""Domain-агрегат Order (issue #372, ADR 0016). PK — самостоятельный
синтетический `uuid.UUID` (не производный от `cart_id`/`user_id`, D4:
пользователь может оформить несколько заказов).

`OrderStatus` — внешний, прескрайбленный ADR 0016:7 набор, не раскрывающий
внутренний Saga Step; `OrderSagaStep` — внутреннее состояние, отдельное поле
(D4). #372 достигает только `PENDING`/`FAILED` — `COMPLETED`/`CANCELLED`/
`EXPIRED` требуют шагов Saga за пределами этого тикета (#373+).

Конструктор вызывается только через `create()` (новый заказ) или
`reconstitute()` (гидратация из БД)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity

_MISSING = object()


class OrderStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class OrderSagaStep(Enum):
    AWAITING_RESERVATION = "awaiting_reservation"
    RESERVATION_CONFIRMED = "reservation_confirmed"
    RESERVATION_FAILED = "reservation_failed"


@dataclass
class OrderLine:
    """Дочерняя сущность агрегата `Order` — plain `uuid.UUID` id, тот же
    прецедент, что `CartLine`/`ReservationLine`. `unit_price_kopecks` —
    коммерческий снимок из авторитетного Catalog quote, не пересчитывается
    позже (ADR 0016:5,9,17)."""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price_kopecks: int


class Order(Entity[uuid.UUID]):
    def __init__(
        self,
        marker: object = _MISSING,
        id: uuid.UUID = cast("uuid.UUID", _MISSING),
        *,
        user_id: uuid.UUID,
        status: OrderStatus,
        saga_step: OrderSagaStep,
        lines: list[OrderLine],
        failure_reason: str | None,
        created_at: datetime,
    ) -> None:
        super().__init__(marker, id=id)
        self.user_id = user_id
        self.status = status
        self.saga_step = saga_step
        self.lines = lines
        self.failure_reason = failure_reason
        self.created_at = created_at

    @classmethod
    def create(
        cls, id: uuid.UUID, *, user_id: uuid.UUID, lines: list[OrderLine]
    ) -> "Order":
        return cls(
            PRIVATE_MARKER,
            id,
            user_id=user_id,
            status=OrderStatus.PENDING,
            saga_step=OrderSagaStep.AWAITING_RESERVATION,
            lines=lines,
            failure_reason=None,
            created_at=datetime.now(UTC),
        )

    @classmethod
    def reconstitute(
        cls,
        id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        status: OrderStatus,
        saga_step: OrderSagaStep,
        lines: list[OrderLine],
        failure_reason: str | None,
        created_at: datetime,
    ) -> "Order":
        return cls(
            PRIVATE_MARKER,
            id,
            user_id=user_id,
            status=status,
            saga_step=saga_step,
            lines=lines,
            failure_reason=failure_reason,
            created_at=created_at,
        )

    def apply_reservation_result(
        self, *, confirmed_product_ids: frozenset[uuid.UUID]
    ) -> bool:
        """Применяет факт `inventory.reserved.v1` (issue #372, D7). Возвращает
        `False` без мутации, если Saga уже покинула `AWAITING_RESERVATION` —
        двухслойная идемпотентность (issue #367's прецедент): вызывающий
        (event-consumer) уже прошёл `processed_messages`-гейт по `message_id`,
        этот guard дополнительно ловит повторную доставку с ДРУГИМ
        `message_id`, несущую тот же бизнес-факт."""
        if self.saga_step is not OrderSagaStep.AWAITING_RESERVATION:
            return False

        if not confirmed_product_ids:
            self.status = OrderStatus.FAILED
            self.saga_step = OrderSagaStep.RESERVATION_FAILED
            self.failure_reason = "NO_ITEMS_AVAILABLE"
            return True

        self.lines = [
            line for line in self.lines if line.product_id in confirmed_product_ids
        ]
        self.saga_step = OrderSagaStep.RESERVATION_CONFIRMED
        return True

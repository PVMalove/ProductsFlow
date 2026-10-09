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
    RESERVATION_FAILED = "reservation_failed"
    # issue #375, D1: заменяет `reservation_confirmed` (#372) — после резерва
    # Saga ждёт результата `payment.authorize.v1`.
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    AWAITING_ALLOCATION = "awaiting_allocation"
    # Отказ/таймаут авторизации: Order уже `FAILED`, резерв ещё освобождается.
    COMPENSATING = "compensating"
    # Резерв освобождён, строки возвращены в Cart; Order остаётся в истории.
    COMPENSATED = "compensated"


class AuthorizationOutcome(Enum):
    """issue #375, D1: результат `payment.authorize.v1` — по одному на каждый
    факт payment-service (`payment.authorized.v1`,
    `payment.authorization_declined.v1`, `payment.authorization_timed_out.v1`)."""

    AUTHORIZED = "authorized"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"


FAILURE_REASON_PAYMENT_DECLINED = "PAYMENT_DECLINED"
FAILURE_REASON_PAYMENT_TIMED_OUT = "PAYMENT_TIMED_OUT"


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
        payment_authorization_id: uuid.UUID | None,
    ) -> None:
        super().__init__(marker, id=id)
        self.user_id = user_id
        self.status = status
        self.saga_step = saga_step
        self.lines = lines
        self.failure_reason = failure_reason
        self.created_at = created_at
        self.payment_authorization_id = payment_authorization_id

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
            payment_authorization_id=None,
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
        payment_authorization_id: uuid.UUID | None = None,
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
            payment_authorization_id=payment_authorization_id,
        )

    def authorization_amount_kopecks(self) -> int:
        """issue #375, D1/DoD 1: сумма к авторизации — только строки,
        подтверждённые резервом. После `apply_reservation_result` `lines` уже
        усечены до подтверждённых, поэтому исходный полный итог Cart сюда не
        попадает."""
        return sum(line.quantity * line.unit_price_kopecks for line in self.lines)

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
        self.saga_step = OrderSagaStep.AWAITING_AUTHORIZATION
        return True

    def apply_authorization_result(
        self, *, outcome: AuthorizationOutcome, authorization_id: uuid.UUID
    ) -> bool:
        """Применяет результат `payment.authorize.v1` (issue #375, D1).
        Возвращает `False` без мутации вне `AWAITING_AUTHORIZATION` — та же
        двухслойная идемпотентность, что `apply_reservation_result`.

        Успех сохраняет `authorization_id` и переводит Saga к allocation
        (статус остаётся `PENDING`). Отказ/таймаут — компенсируемый
        терминальный результат: внешний статус сразу `FAILED`, Saga переходит
        в `COMPENSATING` (резерв освобождается отдельным шагом)."""
        if self.saga_step is not OrderSagaStep.AWAITING_AUTHORIZATION:
            return False

        if outcome is AuthorizationOutcome.AUTHORIZED:
            self.payment_authorization_id = authorization_id
            self.saga_step = OrderSagaStep.AWAITING_ALLOCATION
            return True

        self.status = OrderStatus.FAILED
        self.failure_reason = (
            FAILURE_REASON_PAYMENT_DECLINED
            if outcome is AuthorizationOutcome.DECLINED
            else FAILURE_REASON_PAYMENT_TIMED_OUT
        )
        self.saga_step = OrderSagaStep.COMPENSATING
        return True

    def complete_compensation(self) -> bool:
        """Фиксирует освобождение резерва (`inventory.released.v1`, issue
        #375, D1). `False` без мутации вне `COMPENSATING` (повторная доставка
        или release в другом шаге). `lines` не усекаются: Order остаётся в
        истории со своими строками и статусом `FAILED`."""
        if self.saga_step is not OrderSagaStep.COMPENSATING:
            return False
        self.saga_step = OrderSagaStep.COMPENSATED
        return True

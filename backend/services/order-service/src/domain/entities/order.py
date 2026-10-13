# ruff: noqa: E501
"""Domain-агрегат Order (issue #372, ADR 0016). PK — самостоятельный
синтетический `uuid.UUID` (не производный от `cart_id`/`user_id`, D4:
пользователь может оформить несколько заказов).

`OrderStatus` — внешний, прескрайбленный ADR 0016:7 набор, не раскрывающий
внутренний Saga Step; `OrderSagaStep` — внутреннее состояние, отдельное поле
(D4). Saga достигает `PENDING`/`FAILED` (#372/#375) и `COMPLETED` после
подтверждённого capture (#376); `CANCELLED` (отмена владельцем) и `EXPIRED`
(истечение резерва) — #377: оба допустимы только для `PENDING` до запроса
capture и компенсируются теми же шагами `COMPENSATING`/`COMPENSATED`.

Конструктор вызывается только через `create()` (новый заказ) или
`reconstitute()` (гидратация из БД)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity

from domain.events.order_domain_event import OrderCompleted

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
    # issue #376, D1: резерв переведён в allocation — Saga ждёт результата
    # `payment.capture.v1`.
    AWAITING_CAPTURE = "awaiting_capture"
    # Терминал успешной Saga: capture подтверждён, Order `COMPLETED`. Имя
    # шага нарочно отличается от значения `OrderStatus` (CONTEXT.md).
    CAPTURED = "captured"
    # Терминальный внешний статус уже выставлен (`FAILED` после отказа/
    # таймаута авторизации, `CANCELLED` после отмены), резерв ещё
    # освобождается.
    COMPENSATING = "compensating"
    # Резерв освобождён, строки возвращены в Cart; Order остаётся в истории
    # со своим терминальным статусом (`FAILED`/`CANCELLED`/`EXPIRED`).
    COMPENSATED = "compensated"


class AuthorizationOutcome(Enum):
    """issue #375, D1: результат `payment.authorize.v1` — по одному на каждый
    факт payment-service (`payment.authorized.v1`,
    `payment.authorization_declined.v1`, `payment.authorization_timed_out.v1`)."""

    AUTHORIZED = "authorized"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"


class ReleaseReason(StrEnum):
    """issue #377, D7: `reason` факта `inventory.released.v1` — резерв
    освобождён по команде Saga (`MANUAL`) либо истёк по TTL (`EXPIRED`)."""

    MANUAL = "manual"
    EXPIRED = "expired"


class ReservationReleaseOutcome(Enum):
    """issue #377: что сделал `Order.apply_reservation_release` — вызывающий
    выбирает по исходу побочные эффекты (void, Cart)."""

    # Нет перехода (повтор, терминал, `AWAITING_CAPTURE`, `manual` вне
    # `COMPENSATING`).
    IGNORED = "ignored"
    # `COMPENSATING` -> `COMPENSATED`: строки Order уже забраны из Cart,
    # возвращаются в него.
    COMPENSATION_COMPLETED = "compensation_completed"
    # Истечение после результата резерва: строки Order забраны из Cart —
    # вызывающий аннулирует сохранённую авторизацию и возвращает строки.
    EXPIRED_LINES_TAKEN = "expired_lines_taken"
    # Истечение в `AWAITING_RESERVATION`: строки ещё в Cart под блокировкой
    # этого Order — вызывающий только разблокирует их.
    EXPIRED_LINES_LOCKED = "expired_lines_locked"


FAILURE_REASON_PAYMENT_DECLINED = "PAYMENT_DECLINED"
FAILURE_REASON_PAYMENT_TIMED_OUT = "PAYMENT_TIMED_OUT"
# issue #377, D1: `failure_reason` несёт и причину отмены/истечения — она же
# попадает в `unavailable_reason` возвращённых строк Cart.
FAILURE_REASON_CANCELLED_BY_CUSTOMER = "CANCELLED_BY_CUSTOMER"
FAILURE_REASON_RESERVATION_EXPIRED = "RESERVATION_EXPIRED"

# issue #377, D1/R1: «до capture» — до запроса `payment.capture.v1`. В
# `AWAITING_CAPTURE` capture уже отправлен: void после него — тихий no-op
# payment-service, void до него отправляет capture в DLQ.
_STEPS_BEFORE_CAPTURE = frozenset(
    {
        OrderSagaStep.AWAITING_RESERVATION,
        OrderSagaStep.AWAITING_AUTHORIZATION,
        OrderSagaStep.AWAITING_ALLOCATION,
    }
)


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
        `message_id`, несущую тот же бизнес-факт.

        issue #377, D1: Order, отменённый, пока резерв был в пути, сохраняет
        статус и причину; результат резерва решает только компенсацию.
        Отменённый с подтверждёнными строками — `COMPENSATING` (строки усечены
        до подтверждённых, резерв надо освободить); иначе — `COMPENSATED`
        (резерва нет). Истёкший Order сюда не попадает: `expire` сразу
        `COMPENSATED`, поздний результат отсекает guard выше."""
        if self.saga_step is not OrderSagaStep.AWAITING_RESERVATION:
            return False

        if self.status is not OrderStatus.PENDING:
            if self.status is OrderStatus.CANCELLED and confirmed_product_ids:
                self.lines = [
                    line
                    for line in self.lines
                    if line.product_id in confirmed_product_ids
                ]
                self.saga_step = OrderSagaStep.COMPENSATING
            else:
                self.saga_step = OrderSagaStep.COMPENSATED
            return True

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

    def apply_allocation_result(self) -> bool:
        """Применяет факт `inventory.allocated.v1` (issue #376, D1): Saga
        переходит к capture, статус остаётся `PENDING`. Возвращает `False`
        без мутации вне `AWAITING_ALLOCATION` — та же двухслойная
        идемпотентность: повтор с другим `message_id` и результат не в своём
        шаге не продвигают Saga."""
        if self.saga_step is not OrderSagaStep.AWAITING_ALLOCATION:
            return False
        self.saga_step = OrderSagaStep.AWAITING_CAPTURE
        return True

    def apply_capture_result(
        self, *, authorization_id: uuid.UUID, causation_id: uuid.UUID
    ) -> bool:
        """Применяет факт `payment.captured.v1` (issue #376, D1): Order
        `COMPLETED`, Saga в терминальном `CAPTURED`, одно событие
        `OrderCompleted` для transactional outbox. Возвращает `False` без
        мутации и без события вне `AWAITING_CAPTURE` (повторная доставка,
        capture раньше allocation, любой результат после `CAPTURED`) и для
        capture чужой авторизации (`authorization_id` не совпадает с
        сохранённым `payment_authorization_id`)."""
        if self.saga_step is not OrderSagaStep.AWAITING_CAPTURE:
            return False
        if authorization_id != self.payment_authorization_id:
            return False
        self.status = OrderStatus.COMPLETED
        self.saga_step = OrderSagaStep.CAPTURED
        self.add_domain_event(
            OrderCompleted(order_id=self.id, causation_id=causation_id)
        )
        return True

    def complete_compensation(self) -> bool:
        """Фиксирует освобождение резерва (`inventory.released.v1`, issue
        #375, D1). `False` без мутации вне `COMPENSATING` (повторная доставка
        или release в другом шаге). `lines` не усекаются: Order остаётся в
        истории со своими строками и терминальным статусом (`FAILED` или
        `CANCELLED`, issue #377)."""
        if self.saga_step is not OrderSagaStep.COMPENSATING:
            return False
        self.saga_step = OrderSagaStep.COMPENSATED
        return True

    def cancel(self) -> bool:
        """Отмена владельцем (issue #377, D1). `False` без мутации, если
        Order не `PENDING` или Saga уже запросила capture. Иначе Order
        `CANCELLED` с причиной `CANCELLED_BY_CUSTOMER` и Saga в
        `COMPENSATING` (вызывающий освобождает резерв и аннулирует сохранённую
        авторизацию). В `AWAITING_RESERVATION` шаг сохраняется: результат
        резерва в пути, компенсацию решает `apply_reservation_result`."""
        if not self._terminate_before_capture(
            OrderStatus.CANCELLED, FAILURE_REASON_CANCELLED_BY_CUSTOMER
        ):
            return False
        if self.saga_step is not OrderSagaStep.AWAITING_RESERVATION:
            self.saga_step = OrderSagaStep.COMPENSATING
        return True

    def expire(self) -> bool:
        """Истечение резерва (`inventory.released.v1` с `reason=expired`,
        issue #377, D1). Тот же guard, что `cancel`: `False` без мутации, если
        Order не `PENDING` или Saga уже запросила capture (allocated резерв
        не истекает). Иначе Order `EXPIRED` с причиной `RESERVATION_EXPIRED`
        и Saga сразу `COMPENSATED` — inventory уже освободил резерв, а
        поздний `inventory.reserved.v1` отсекается guard'ом
        `apply_reservation_result`."""
        if not self._terminate_before_capture(
            OrderStatus.EXPIRED, FAILURE_REASON_RESERVATION_EXPIRED
        ):
            return False
        self.saga_step = OrderSagaStep.COMPENSATED
        return True

    def apply_reservation_release(
        self, *, reason: ReleaseReason
    ) -> ReservationReleaseOutcome:
        """Применяет факт `inventory.released.v1` (issue #375 D1, #377 D4/D7)
        и возвращает исход. В `COMPENSATING` любой `reason` завершает
        компенсацию: резерв освобождён в обоих случаях. Иначе только
        `reason=expired` что-то меняет: `PENDING` до запроса capture истекает
        (`expire`), а отменённый, пока результат резерва был в пути
        (`CANCELLED` + `AWAITING_RESERVATION`), сразу `COMPENSATED` — статус и
        причина отмены сохраняются. Остальное — `IGNORED` без мутации."""
        if self.complete_compensation():
            return ReservationReleaseOutcome.COMPENSATION_COMPLETED
        if reason is not ReleaseReason.EXPIRED:
            return ReservationReleaseOutcome.IGNORED

        in_flight = self.saga_step is OrderSagaStep.AWAITING_RESERVATION
        if self.status is OrderStatus.CANCELLED and in_flight:
            self.saga_step = OrderSagaStep.COMPENSATED
            return ReservationReleaseOutcome.EXPIRED_LINES_LOCKED
        if not self.expire():
            return ReservationReleaseOutcome.IGNORED
        if in_flight:
            return ReservationReleaseOutcome.EXPIRED_LINES_LOCKED
        return ReservationReleaseOutcome.EXPIRED_LINES_TAKEN

    def record_late_authorization(self, *, authorization_id: uuid.UUID) -> bool:
        """Фиксирует успешную авторизацию, пришедшую после отмены или
        истечения Order (issue #377, D1): вызывающий обязан её аннулировать
        (`payment.void.v1`). `False` без мутации для любого другого статуса и
        для уже сохранённой авторизации (повторный факт не ставит второй
        void)."""
        if self.status not in (OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            return False
        if self.payment_authorization_id is not None:
            return False
        self.payment_authorization_id = authorization_id
        return True

    def _terminate_before_capture(self, status: OrderStatus, reason: str) -> bool:
        """Общий скелет `cancel`/`expire` (issue #377): guard «`PENDING` до
        запроса capture», затем терминальный статус и причина. Шаг Saga
        выставляет вызывающий."""
        if not self._is_pending_before_capture():
            return False
        self.status = status
        self.failure_reason = reason
        return True

    def _is_pending_before_capture(self) -> bool:
        return (
            self.status is OrderStatus.PENDING
            and self.saga_step in _STEPS_BEFORE_CAPTURE
        )

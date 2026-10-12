# ruff: noqa: E501
"""Команда и handler отмены заказа владельцем (issue #377, D4/D5) — одна
локальная транзакция: Order под блокировкой строки -> переход `CANCELLED` ->
intents компенсации (`payment.void.v1`, `inventory.release.v1`),
all-or-nothing. Строки возвращаются в Cart позже, по факту
`inventory.released.v1` (`ApplyReservationReleaseCommandHandler`)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from application.errors import OrderAccessDeniedError, OrderNotFoundError
from contracts.order import OrderView
from domain.entities.order import OrderSagaStep, OrderStatus
from domain.errors import OrderErrors
from domain.unit_of_work import OrderCancellationUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CancelOrderCommand:
    actor: Actor
    order_id: uuid.UUID


class CancelOrderCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Отмена владельцем PENDING Order до запроса capture (ADR 0016, issue #377).
    Validations: `order_id` должен существовать (404) и принадлежать вызывающему (403) — обе проверки ДО мутации домена; Order не PENDING или Saga уже запросила capture — Result-ошибка order_not_cancellable (409), ничего не меняется. Повтор отмены уже CANCELLED Order — успех без новых intent'ов.
    Side Effects: Order -> CANCELLED (CANCELLED_BY_CUSTOMER) под SELECT ... FOR UPDATE; вне AWAITING_RESERVATION Saga -> COMPENSATING и intent inventory.release.v1; сохранённая авторизация -> intent payment.void.v1. В AWAITING_RESERVATION команд нет: компенсацию решает результат резерва в пути.
    """

    def __init__(self, uow: OrderCancellationUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: CancelOrderCommand) -> Result[OrderView]:
        async with self._uow:
            order = await self._uow.orders.get_locked_by_id(command.order_id)
            if order is None:
                logger.warning(
                    "Отмена заказа отклонена: order_id=%s не найден",
                    command.order_id,
                )
                raise OrderNotFoundError
            if order.user_id != command.actor.id:
                logger.warning(
                    "Отмена заказа отклонена: order_id=%s принадлежит другому пользователю",
                    command.order_id,
                )
                raise OrderAccessDeniedError

            if order.status is OrderStatus.CANCELLED:
                logger.info(
                    "Отмена заказа: order_id=%s уже отменён — повтор без изменений",
                    command.order_id,
                )
                return Result[OrderView].ok(OrderView.from_domain(order))

            if not order.cancel():
                logger.warning(
                    "Отмена заказа отклонена: order_id=%s status=%s saga_step=%s",
                    command.order_id,
                    order.status.value,
                    order.saga_step.value,
                )
                return Result[OrderView].fail(OrderErrors.order_not_cancellable())

            await self._uow.orders.save(order)
            if order.payment_authorization_id is not None:
                await self._uow.saga_command_outbox.enqueue_void(
                    order_id=order.id,
                    authorization_id=order.payment_authorization_id,
                )
            if order.saga_step is OrderSagaStep.COMPENSATING:
                await self._uow.saga_command_outbox.enqueue_release(order_id=order.id)
            await self._uow.commit()

        logger.info(
            "Заказ отменён владельцем: order_id=%s saga_step=%s",
            order.id,
            order.saga_step.value,
        )
        return Result[OrderView].ok(OrderView.from_domain(order))

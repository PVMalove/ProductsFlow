"""Пишущая сторона `reservation_outbox` (issue #372, D6; issue #375, D3).

Таблица несёт все исходящие команды Saga, не только `inventory.reserve.v1`
— имя таблицы/класса осталось от #372 (naming debt R5 брифа #375,
переименование — отдельный рефакторинг). Тип команды и wire-payload — забота
этого модуля: доменный порт называет только намерение."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.order import OrderLine
from domain.repositories import (
    ReservationOutboxRepository as ReservationOutboxRepositoryPort,
)
from infrastructure.db.entity_configurations.models import ReservationOutboxModel

RESERVE_COMMAND_TYPE = "inventory.reserve.v1"
AUTHORIZE_COMMAND_TYPE = "payment.authorize.v1"
# Все типы, которые order-worker публикует — для объявления command-топологии.
COMMAND_TYPES = (RESERVE_COMMAND_TYPE, AUTHORIZE_COMMAND_TYPE)


class ReservationOutboxRepository:
    """Используется application-handler'ами внутри их транзакции.
    Дренаж/публикация — забота отдельного `ReservationOutboxPublisher` (не
    этого класса), тот же разрыв, что generic `OutboxPublisher` vs доменные
    `add_domain_event`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, *, order_id: uuid.UUID, lines: list[OrderLine]) -> None:
        self._add(
            order_id=order_id,
            command_type=RESERVE_COMMAND_TYPE,
            payload={
                "order_id": str(order_id),
                "lines": [
                    {"product_id": str(line.product_id), "quantity": line.quantity}
                    for line in lines
                ],
            },
        )

    async def enqueue_authorization(
        self, *, order_id: uuid.UUID, amount_kopecks: int, payment_method_token: str
    ) -> None:
        # Ключи payload — ровно те, что читает payment-service's
        # `handle_authorize_command` (`amount`, `payment_method_token`).
        self._add(
            order_id=order_id,
            command_type=AUTHORIZE_COMMAND_TYPE,
            payload={
                "amount": amount_kopecks,
                "payment_method_token": payment_method_token,
            },
        )

    def _add(
        self, *, order_id: uuid.UUID, command_type: str, payload: dict[str, Any]
    ) -> None:
        self.session.add(
            ReservationOutboxModel(
                id=uuid.uuid4(),
                order_id=order_id,
                command_type=command_type,
                payload=payload,
            )
        )


_reservation_outbox_repository_implementation: type[ReservationOutboxRepositoryPort] = (
    ReservationOutboxRepository
)

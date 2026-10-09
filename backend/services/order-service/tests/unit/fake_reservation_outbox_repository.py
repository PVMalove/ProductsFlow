"""Фейковый ReservationOutboxRepository для юнит-тестов (issue #372;
issue #375 — authorization intent)."""

import uuid
from dataclasses import dataclass

from domain.entities.order import OrderLine


@dataclass(frozen=True)
class AuthorizationIntent:
    order_id: uuid.UUID
    amount_kopecks: int
    payment_method_token: str


class FakeReservationOutboxRepository:
    def __init__(self) -> None:
        self.enqueue_calls: list[tuple[uuid.UUID, list[OrderLine]]] = []
        self.authorization_intents: list[AuthorizationIntent] = []

    async def enqueue(self, *, order_id: uuid.UUID, lines: list[OrderLine]) -> None:
        self.enqueue_calls.append((order_id, lines))

    async def enqueue_authorization(
        self, *, order_id: uuid.UUID, amount_kopecks: int, payment_method_token: str
    ) -> None:
        self.authorization_intents.append(
            AuthorizationIntent(
                order_id=order_id,
                amount_kopecks=amount_kopecks,
                payment_method_token=payment_method_token,
            )
        )

"""Фейковый SagaCommandOutboxRepository для юнит-тестов (issue #372;
issue #375 — authorization/release intents; issue #376 — allocation/capture
intents; issue #377 — void intents)."""

import uuid
from dataclasses import dataclass

from domain.entities.order import OrderLine


@dataclass(frozen=True)
class AuthorizationIntent:
    order_id: uuid.UUID
    amount_kopecks: int
    payment_method_token: str


@dataclass(frozen=True)
class CaptureIntent:
    order_id: uuid.UUID
    authorization_id: uuid.UUID


@dataclass(frozen=True)
class VoidIntent:
    order_id: uuid.UUID
    authorization_id: uuid.UUID


class FakeSagaCommandOutboxRepository:
    def __init__(self) -> None:
        self.enqueue_calls: list[tuple[uuid.UUID, list[OrderLine]]] = []
        self.authorization_intents: list[AuthorizationIntent] = []
        self.release_intents: list[uuid.UUID] = []
        self.allocation_intents: list[uuid.UUID] = []
        self.capture_intents: list[CaptureIntent] = []
        self.void_intents: list[VoidIntent] = []

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

    async def enqueue_release(self, *, order_id: uuid.UUID) -> None:
        self.release_intents.append(order_id)

    async def enqueue_allocation(self, *, order_id: uuid.UUID) -> None:
        self.allocation_intents.append(order_id)

    async def enqueue_capture(
        self, *, order_id: uuid.UUID, authorization_id: uuid.UUID
    ) -> None:
        self.capture_intents.append(
            CaptureIntent(order_id=order_id, authorization_id=authorization_id)
        )

    async def enqueue_void(
        self, *, order_id: uuid.UUID, authorization_id: uuid.UUID
    ) -> None:
        self.void_intents.append(
            VoidIntent(order_id=order_id, authorization_id=authorization_id)
        )

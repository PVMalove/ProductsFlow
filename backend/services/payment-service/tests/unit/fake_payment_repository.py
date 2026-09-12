"""Фейковый PaymentAuthorizationRepository для юнит-тестов application
handler'ов (issue #368)."""

import uuid

from domain.entities.payment_authorization import PaymentAuthorization


class FakePaymentAuthorizationRepository:
    def __init__(self, payments: list[PaymentAuthorization] | None = None) -> None:
        self._by_id: dict[uuid.UUID, PaymentAuthorization] = {
            payment.id: payment for payment in (payments or [])
        }
        self.add_calls: list[PaymentAuthorization] = []
        self.save_calls: list[PaymentAuthorization] = []

    async def get_by_idempotency_key(self, key: str) -> PaymentAuthorization | None:
        for payment in self._by_id.values():
            if key in (
                payment.idempotency_key,
                payment.void_idempotency_key,
                payment.capture_idempotency_key,
            ):
                return payment
        return None

    async def get_by_id(self, id: uuid.UUID) -> PaymentAuthorization | None:
        return self._by_id.get(id)

    async def add(self, payment: PaymentAuthorization) -> bool:
        self.add_calls.append(payment)
        already_exists = any(
            existing.idempotency_key == payment.idempotency_key
            for existing in self._by_id.values()
        )
        if already_exists:
            return False
        self._by_id[payment.id] = payment
        return True

    async def save(self, payment: PaymentAuthorization) -> None:
        self.save_calls.append(payment)
        self._by_id[payment.id] = payment

"""Framework-independent контракт вывода для команд/запросов payment
(ADR 0002) — application-хендлеры возвращают его, HTTP только сериализует."""

import uuid
from dataclasses import dataclass

from domain.entities.payment_authorization import PaymentAuthorization


@dataclass(frozen=True)
class PaymentAuthorizationView:
    id: uuid.UUID
    idempotency_key: str
    amount: int
    payment_method_token: str
    status: str

    @classmethod
    def from_domain(cls, payment: PaymentAuthorization) -> "PaymentAuthorizationView":
        return cls(
            id=payment.id,
            idempotency_key=payment.idempotency_key,
            amount=payment.amount,
            payment_method_token=payment.payment_method_token,
            status=payment.status.value,
        )

import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.payment_authorization import (
    PaymentAuthorization,
    PaymentAuthorizationStatus,
)
from domain.repositories import (
    PaymentAuthorizationRepository as PaymentAuthorizationRepositoryPort,
)
from infrastructure.db.entity_configurations.models import PaymentAuthorizationModel


def _to_domain(row: PaymentAuthorizationModel) -> PaymentAuthorization:
    return PaymentAuthorization.reconstitute(
        row.id,
        idempotency_key=row.idempotency_key,
        amount=row.amount,
        payment_method_token=row.payment_method_token,
        status=PaymentAuthorizationStatus(row.status),
        void_idempotency_key=row.void_idempotency_key,
        capture_idempotency_key=row.capture_idempotency_key,
        created_at=row.created_at,
    )


class PaymentAuthorizationRepository:
    """CRUD для `PaymentAuthorization` (issue #368). Никакого outbox-дренажа
    — payment-service не эмитит доменных событий в этом тикете (архитектурный
    бриф D1); фиксация транзакции принадлежит `PaymentUnitOfWork` (ADR 0006) —
    этот адаптер никогда не коммитит самостоятельно."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency_key(self, key: str) -> PaymentAuthorization | None:
        row = await self.session.scalar(
            select(PaymentAuthorizationModel).where(
                or_(
                    PaymentAuthorizationModel.idempotency_key == key,
                    PaymentAuthorizationModel.void_idempotency_key == key,
                    PaymentAuthorizationModel.capture_idempotency_key == key,
                )
            )
        )
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, id: uuid.UUID) -> PaymentAuthorization | None:
        row = await self.session.scalar(
            select(PaymentAuthorizationModel)
            .where(PaymentAuthorizationModel.id == id)
            .with_for_update()
        )
        return _to_domain(row) if row is not None else None

    async def add(self, payment: PaymentAuthorization) -> bool:
        inserted_id = await self.session.scalar(
            pg_insert(PaymentAuthorizationModel)
            .values(
                id=payment.id,
                idempotency_key=payment.idempotency_key,
                amount=payment.amount,
                payment_method_token=payment.payment_method_token,
                status=payment.status.value,
                void_idempotency_key=payment.void_idempotency_key,
                capture_idempotency_key=payment.capture_idempotency_key,
                created_at=payment.created_at,
            )
            .on_conflict_do_nothing(
                index_elements=[PaymentAuthorizationModel.idempotency_key]
            )
            .returning(PaymentAuthorizationModel.id)
        )
        return inserted_id is not None

    async def save(self, payment: PaymentAuthorization) -> None:
        row = await self.session.get(PaymentAuthorizationModel, payment.id)
        assert row is not None
        row.status = payment.status.value
        row.void_idempotency_key = payment.void_idempotency_key
        row.capture_idempotency_key = payment.capture_idempotency_key


# Статическая структурная проверка: mypy убеждается, что конкретная
# реализация удовлетворяет каждую операцию, требуемую доменным контрактом
# репозитория.
_payment_authorization_repository_implementation: type[
    PaymentAuthorizationRepositoryPort
] = PaymentAuthorizationRepository

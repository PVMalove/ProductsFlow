import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.repositories import IdempotencyKeyRepository as IdempotencyKeyRepositoryPort
from infrastructure.db.entity_configurations.models import IdempotencyKeyModel


class IdempotencyKeyRepository:
    """CRUD для Idempotency-Key записей (issue #372, D2) — insert-only,
    composite PK `(user_id, key)` закрепляет буквальную HTTP-семантику уже
    на уровне схемы."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, user_id: uuid.UUID, key: str
    ) -> IdempotencyKeyRecord | None:
        row = await self.session.scalar(
            select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.user_id == user_id,
                IdempotencyKeyModel.key == key,
            )
        )
        if row is None:
            return None
        return IdempotencyKeyRecord(
            user_id=row.user_id,
            key=row.key,
            request_fingerprint=row.request_fingerprint,
            order_id=row.order_id,
            created_at=row.created_at,
        )

    async def save(self, record: IdempotencyKeyRecord) -> None:
        self.session.add(
            IdempotencyKeyModel(
                user_id=record.user_id,
                key=record.key,
                request_fingerprint=record.request_fingerprint,
                order_id=record.order_id,
                created_at=record.created_at,
            )
        )


_idempotency_key_repository_implementation: type[IdempotencyKeyRepositoryPort] = (
    IdempotencyKeyRepository
)

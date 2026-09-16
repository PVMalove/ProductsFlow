"""Фейковый IdempotencyKeyRepository для юнит-тестов (issue #372)."""

import uuid

from domain.entities.idempotency_key import IdempotencyKeyRecord


class FakeIdempotencyKeyRepository:
    def __init__(self) -> None:
        self._by_key: dict[tuple[uuid.UUID, str], IdempotencyKeyRecord] = {}
        self.save_calls: list[IdempotencyKeyRecord] = []

    async def get(self, user_id: uuid.UUID, key: str) -> IdempotencyKeyRecord | None:
        return self._by_key.get((user_id, key))

    async def save(self, record: IdempotencyKeyRecord) -> None:
        self.save_calls.append(record)
        self._by_key[(record.user_id, record.key)] = record

import uuid
from typing import Protocol, runtime_checkable

from domain.entities.payment_authorization import PaymentAuthorization


@runtime_checkable
class PaymentAuthorizationRepository(Protocol):
    """Контракт персистентности агрегата PaymentAuthorization (ADR 0006,
    issue #368). Три idempotency-колонки (authorize/void/capture) живут на
    одном агрегате — `get_by_idempotency_key` ищет совпадение по любой из
    них (архитектурный бриф D3)."""

    async def get_by_idempotency_key(self, key: str) -> PaymentAuthorization | None: ...

    async def get_by_id(self, id: uuid.UUID) -> PaymentAuthorization | None: ...

    async def add(self, payment: PaymentAuthorization) -> bool:
        """Идемпотентно вставляет новую авторизацию. Возвращает `True`, если
        строка была реально вставлена, `False` — при уже существующем
        `idempotency_key` (natural PK-идемпотентность, мирор inventory's
        `create_zero`)."""
        ...

    async def save(self, payment: PaymentAuthorization) -> None:
        """Персистит мутацию уже существующей авторизации (void/capture)."""
        ...

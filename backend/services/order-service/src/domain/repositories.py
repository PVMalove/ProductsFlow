import uuid
from typing import Protocol, runtime_checkable

from domain.entities.cart import Cart
from domain.entities.idempotency_key import IdempotencyKeyRecord
from domain.entities.order import Order, OrderLine


@runtime_checkable
class CartRepository(Protocol):
    """Контракт персистентности агрегата `Cart` (ADR 0006, issue #369)."""

    async def get_or_create_for_user(self, user_id: uuid.UUID) -> Cart:
        """Атомарный get-or-create (D3): `INSERT ... ON CONFLICT(user_id) DO
        NOTHING` + повторное чтение при конфликте — закрывает TOCTOU-гонку
        двух конкурентных первых `AddCartLine`."""
        ...

    async def get_for_user(self, user_id: uuid.UUID) -> Cart | None:
        """Для `GET /api/v1/cart` — без побочного эффекта записи (D3)."""
        ...

    async def get_line_owner(self, line_id: uuid.UUID) -> Cart | None:
        """Возвращает родительский `Cart` строки целиком (без фильтра по
        владельцу — D5 требует увидеть owner, чтобы решить 403 vs 404) или
        `None`, если `line_id` не существует вовсе."""
        ...

    async def save(self, cart: Cart) -> None:
        """Персистит `lines` добавление/upsert/delete по diff (мирует
        `TicketRepository`, не одна SQL-мутация на метод)."""
        ...

    async def get_locked_for_user(self, user_id: uuid.UUID) -> Cart | None:
        """issue #372, D5/Risk 4: та же выборка, что `get_for_user`, но с
        `SELECT ... FOR UPDATE` — checkout обязан удержать блокировку строк
        на время своей транзакции, иначе два параллельных checkout одного
        пользователя могут захватить одни и те же строки."""
        ...

    async def get_locked_by_order(self, order_id: uuid.UUID) -> Cart | None:
        """issue #372, D7: находит `Cart`, чьи строки заблокированы данным
        `order_id` (может отсутствовать вовсе, если Cart уже пуст/не
        существует) — для reservation-result consumer'а."""
        ...


@runtime_checkable
class OrderRepository(Protocol):
    """Контракт персистентности агрегата `Order` (issue #372, D4)."""

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None: ...

    async def save(self, order: Order) -> None:
        """Персистит `lines` по diff (мирует `CartRepository.save`) — набор
        строк только сокращается после создания (D7), никогда не растёт."""
        ...


@runtime_checkable
class IdempotencyKeyRepository(Protocol):
    """Контракт персистентности идемпотентности checkout (issue #372, D2)."""

    async def get(
        self, user_id: uuid.UUID, key: str
    ) -> IdempotencyKeyRecord | None: ...

    async def save(self, record: IdempotencyKeyRecord) -> None: ...


@runtime_checkable
class ReservationOutboxRepository(Protocol):
    """Контракт исходящего command-intent для `inventory.reserve.v1`
    (issue #372, D6) — НЕ переиспользует `kernel_platform.OutboxMessage`
    (типовой конфликт BigInt PK vs UUID `command_id`, находка 5)."""

    async def enqueue(self, *, order_id: uuid.UUID, lines: list[OrderLine]) -> None: ...

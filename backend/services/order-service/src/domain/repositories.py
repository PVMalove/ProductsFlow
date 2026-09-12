import uuid
from typing import Protocol, runtime_checkable

from domain.entities.cart import Cart


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

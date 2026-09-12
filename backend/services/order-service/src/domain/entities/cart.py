import uuid
from datetime import UTC, datetime
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.result import Result

from domain.entities.cart_line import CartLine
from domain.errors import CartErrors
from domain.value_objects.cart_id import CartId

_MISSING = object()


class Cart(Entity[CartId]):
    """Агрегат серверной корзины (issue #369). Один `Cart` на пользователя
    (`UNIQUE(user_id)`, обеспечивается на уровне БД/репозитория, D3). Владеет
    своими `CartLine` — все мутации строк идут только через методы этого
    агрегата. Никаких доменных событий сегодня (архитектурный бриф D1) —
    RabbitMQ/outbox-обвязка вне скоупа #369.

    Конструктор вызывается только через `create()` (новая пустая корзина) или
    `reconstitute()` (гидратация из БД)."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: CartId = cast("CartId", _MISSING),
        *,
        user_id: uuid.UUID,
        lines: list[CartLine] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(marker, id=id)
        self.user_id = user_id
        self.lines = lines if lines is not None else []
        self.created_at = created_at or datetime.now(UTC)

    @classmethod
    def create(cls, id: CartId, *, user_id: uuid.UUID) -> "Cart":
        # Без Result — создание пустой корзины не может провалиться по
        # бизнес-правилу (архитектурный бриф D3/domain design).
        return cls(PRIVATE_MARKER, id, user_id=user_id)

    @classmethod
    def reconstitute(
        cls,
        id: CartId,
        *,
        user_id: uuid.UUID,
        lines: list[CartLine],
        created_at: datetime,
    ) -> "Cart":
        return cls(PRIVATE_MARKER, id, user_id=user_id, lines=lines, created_at=created_at)

    def add_line(
        self, *, line_id: uuid.UUID, product_id: uuid.UUID, quantity: int, now: datetime
    ) -> Result[CartLine]:
        if quantity <= 0:
            return Result[CartLine].fail(CartErrors.invalid_quantity())

        existing = self._line_by_product_id(product_id)
        if existing is not None:
            # D4: повторное добавление того же товара увеличивает quantity
            # уже существующей строки, а не создаёт отдельную запись.
            existing.quantity += quantity
            return Result[CartLine].ok(existing)

        line = CartLine(id=line_id, product_id=product_id, quantity=quantity, added_at=now)
        self.lines.append(line)
        return Result[CartLine].ok(line)

    def update_line_quantity(
        self, *, line_id: uuid.UUID, quantity: int
    ) -> Result[CartLine]:
        if quantity <= 0:
            return Result[CartLine].fail(CartErrors.invalid_quantity())

        line = self._line_by_id(line_id)
        if line is None:
            return Result[CartLine].fail(CartErrors.line_not_found())

        line.quantity = quantity
        return Result[CartLine].ok(line)

    def remove_line(self, *, line_id: uuid.UUID) -> Result[None]:
        line = self._line_by_id(line_id)
        if line is None:
            return Result[None].fail(CartErrors.line_not_found())

        self.lines.remove(line)
        return Result[None].ok(None)

    def _line_by_id(self, line_id: uuid.UUID) -> CartLine | None:
        for line in self.lines:
            if line.id == line_id:
                return line
        return None

    def _line_by_product_id(self, product_id: uuid.UUID) -> CartLine | None:
        for line in self.lines:
            if line.product_id == product_id:
                return line
        return None

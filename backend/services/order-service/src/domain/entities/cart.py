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

# issue #372, D7: единственная причина, по которой строка остаётся в Cart
# после частичного резерва, — `InventoryReserved.unavailable_lines` не несёт
# текстовый reason, только (product_id, requested_quantity).
UNAVAILABLE_REASON_INSUFFICIENT_STOCK = "insufficient_stock"


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
        return cls(
            PRIVATE_MARKER, id, user_id=user_id, lines=lines, created_at=created_at
        )

    def add_line(
        self, *, line_id: uuid.UUID, product_id: uuid.UUID, quantity: int, now: datetime
    ) -> Result[CartLine]:
        if quantity <= 0:
            return Result[CartLine].fail(CartErrors.invalid_quantity())

        existing = self._line_by_product_id(product_id)
        if existing is not None:
            # issue #372, D3: строка, вошедшая в Checkout Selection, не
            # может мутироваться до терминального результата Saga.
            if existing.locked_by_order_id is not None:
                return Result[CartLine].fail(CartErrors.line_locked())
            # D4: повторное добавление того же товара увеличивает quantity
            # уже существующей строки, а не создаёт отдельную запись.
            existing.quantity += quantity
            return Result[CartLine].ok(existing)

        line = CartLine(
            id=line_id, product_id=product_id, quantity=quantity, added_at=now
        )
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
        if line.locked_by_order_id is not None:
            return Result[CartLine].fail(CartErrors.line_locked())

        line.quantity = quantity
        return Result[CartLine].ok(line)

    def remove_line(self, *, line_id: uuid.UUID) -> Result[None]:
        line = self._line_by_id(line_id)
        if line is None:
            return Result[None].fail(CartErrors.line_not_found())
        if line.locked_by_order_id is not None:
            return Result[None].fail(CartErrors.line_locked())

        self.lines.remove(line)
        return Result[None].ok(None)

    def lock_for_checkout(self, *, order_id: uuid.UUID) -> None:
        """issue #372, D3/D5: фиксирует Checkout Selection — блокирует все
        текущие строки корзины на выбранный заказ, атомарно в одной
        транзакции с созданием `Order` (вызывающий отвечает за commit)."""
        for line in self.lines:
            line.locked_by_order_id = order_id

    def has_locked_lines(self) -> bool:
        """issue #372 (code-review fix): true, если хотя бы одна строка уже
        заблокирована активным (нетерминальным) Checkout Selection'ом —
        терминальное разрешение Saga всегда снимает блокировку (`unlock_all`/
        `resolve_partial_reservation`), поэтому непустой
        `locked_by_order_id` однозначно означает ещё не завершённый заказ.
        `CheckoutCommandHandler` использует это, чтобы отклонить второй,
        последовательный checkout той же корзины вместо того, чтобы
        `lock_for_checkout` молча переназначил блокировку на новый заказ."""
        return any(line.locked_by_order_id is not None for line in self.lines)

    def unlock_all(self, *, order_id: uuid.UUID) -> None:
        """issue #372, D7 п.1: нулевой результат резерва — просто снимает
        блокировку, не трогая состав корзины/`unavailable_reason` (AC4)."""
        for line in self.lines:
            if line.locked_by_order_id == order_id:
                line.locked_by_order_id = None

    def resolve_partial_reservation(
        self, *, order_id: uuid.UUID, confirmed_product_ids: frozenset[uuid.UUID]
    ) -> None:
        """issue #372, D7 п.2: подтверждённые строки становятся Order lines
        и физически удаляются из корзины; недоступные — разблокируются и
        помечаются причиной (AC5)."""
        remaining: list[CartLine] = []
        for line in self.lines:
            if line.locked_by_order_id != order_id:
                remaining.append(line)
                continue
            if line.product_id in confirmed_product_ids:
                continue
            line.locked_by_order_id = None
            line.unavailable_reason = UNAVAILABLE_REASON_INSUFFICIENT_STOCK
            remaining.append(line)
        self.lines = remaining

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

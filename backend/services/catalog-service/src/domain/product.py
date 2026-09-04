import uuid

from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.events.product_domain_event import (
    ProductActivated,
    ProductCreated,
    ProductDeactivated,
    ProductDeleted,
    ProductUpdated,
)
from domain.product_id import ProductId

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 100
CATEGORY_MIN_LENGTH = 3
CATEGORY_MAX_LENGTH = 100


def _validate(*, name: str, category: str, price: float) -> Error | None:
    if not (NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH):
        return Error(
            code="invalid_name",
            description=(
                f"Название должно быть от {NAME_MIN_LENGTH} "
                f"до {NAME_MAX_LENGTH} символов"
            ),
            type=ErrorType.VALIDATION,
        )
    if not (CATEGORY_MIN_LENGTH <= len(category) <= CATEGORY_MAX_LENGTH):
        return Error(
            code="invalid_category",
            description=(
                f"Категория должна быть от {CATEGORY_MIN_LENGTH} "
                f"до {CATEGORY_MAX_LENGTH} символов"
            ),
            type=ErrorType.VALIDATION,
        )
    if price < 0:
        return Error(
            code="invalid_price",
            description="Цена не может быть отрицательной",
            type=ErrorType.VALIDATION,
        )
    return None


class Product(Entity[ProductId]):
    """Агрегат Товара (issue #148, ADR 0021). `user_id` — идентификатор
    Владельца из identity-service (`UserId`, GUID); больше не FK в БД catalog
    (Владелец резолвится через `OwnerReadModel`, TD §4.2)."""

    def __init__(
        self,
        id: ProductId,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
        is_active: bool,
    ) -> None:
        super().__init__(id)
        self.name = name
        self.description = description
        self.price = price
        self.category = category
        self.user_id = user_id
        self.is_active = is_active

    @classmethod
    def create(
        cls,
        id: ProductId,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
    ) -> Result["Product"]:
        error = _validate(name=name, category=category, price=price)
        if error is not None:
            return Result[Product].fail(error)

        product = cls(
            id,
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=user_id,
            is_active=True,
        )
        product.add_domain_event(
            ProductCreated(
                product_id=id,
                user_id=user_id,
                name=name,
                category=category,
                price=price,
            )
        )
        return Result[Product].ok(product)

    def update(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        category: str | None = None,
    ) -> Result[None]:
        """Частичное обновление (см. CONTEXT.md «Обновление товара»): `None`
        значит «поле не прислано» — то же самое `exclude_unset`, что применяет
        репозиторий монолита, только на уровне домена, а не `setattr`."""
        error = _validate(
            name=name if name is not None else self.name,
            category=category if category is not None else self.category,
            price=price if price is not None else self.price,
        )
        if error is not None:
            return Result[None].fail(error)

        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if price is not None:
            self.price = price
        if category is not None:
            self.category = category

        self.add_domain_event(ProductUpdated(product_id=self.id))
        return Result[None].ok(None)

    def activate(self) -> Result[None]:
        if self.is_active:
            return Result[None].fail(
                Error(
                    code="already_active",
                    description="Товар уже активен",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = True
        self.add_domain_event(ProductActivated(product_id=self.id))
        return Result[None].ok(None)

    def deactivate(self) -> Result[None]:
        if not self.is_active:
            return Result[None].fail(
                Error(
                    code="already_deactivated",
                    description="Товар уже деактивирован",
                    type=ErrorType.CONFLICT,
                )
            )

        self.is_active = False
        self.add_domain_event(ProductDeactivated(product_id=self.id))
        return Result[None].ok(None)

    def mark_deleted(self) -> None:
        """Удаление — не переход состояния агрегата (строка просто исчезает
        из БД, CONTEXT.md «Удаление»), но само событие всё равно должно уйти
        в Outbox — репозиторий вызывает это перед `session.delete()`."""
        self.add_domain_event(ProductDeleted(product_id=self.id))

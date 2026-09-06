import uuid
from datetime import UTC, datetime
from typing import TypedDict, cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.errors import Error, ErrorList
from kernel_domain.result import Result

from domain.errors import CatalogErrors
from domain.events.product_domain_event import (
    ProductActivated,
    ProductCreated,
    ProductDeactivated,
    ProductDeleted,
    ProductUpdated,
)
from domain.value_objects.product_id import ProductId

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 100
CATEGORY_MIN_LENGTH = 3
CATEGORY_MAX_LENGTH = 100

_MISSING = object()


class _SnapshotEventFields(TypedDict):
    product_id: ProductId
    user_id: uuid.UUID
    name: str
    description: str
    category: str
    price: float
    is_active: bool
    search_revision: int
    created_at: datetime


def _validate(*, name: str, category: str, price: float) -> Error | None:
    errors: list[Error] = []
    if not (NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH):
        errors.append(CatalogErrors.invalid_name(NAME_MIN_LENGTH, NAME_MAX_LENGTH))
    if not (CATEGORY_MIN_LENGTH <= len(category) <= CATEGORY_MAX_LENGTH):
        errors.append(
            CatalogErrors.invalid_category(CATEGORY_MIN_LENGTH, CATEGORY_MAX_LENGTH)
        )
    if price < 0:
        errors.append(CatalogErrors.invalid_price())
    if not errors:
        return None
    return ErrorList.of(errors)


class Product(Entity[ProductId]):
    """Агрегат Товара (issue #148, ADR 0011). `user_id` — идентификатор
    Владельца из identity-service (`UserId`, GUID); больше не FK в БД catalog
    (Владелец резолвится через `OwnerReadModel`, TD §4.2).

    Конструктор вызывается только через `create()` (новый товар) или
    `reconstitute()` (гидратация из БД) — маркер приватности проверяется
    централизованно в `Entity.__init__`."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: ProductId = cast("ProductId", _MISSING),
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
        is_active: bool,
        search_revision: int = 1,
        created_at: datetime = cast("datetime", _MISSING),
    ) -> None:
        super().__init__(marker, id=id)
        self.name = name
        self.description = description
        self.price = price
        self.category = category
        self.user_id = user_id
        self.is_active = is_active
        self.search_revision = search_revision
        self.created_at = created_at

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
            PRIVATE_MARKER,
            id,
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=user_id,
            is_active=True,
            search_revision=1,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        product.add_domain_event(
            ProductCreated(
                **product._snapshot_event_fields(),
            )
        )
        return Result[Product].ok(product)

    @classmethod
    def reconstitute(
        cls,
        id: ProductId,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
        is_active: bool,
        search_revision: int = 1,
        created_at: datetime,
    ) -> "Product":
        return cls(
            PRIVATE_MARKER,
            id,
            name=name,
            description=description,
            price=price,
            category=category,
            user_id=user_id,
            is_active=is_active,
            search_revision=search_revision,
            created_at=created_at,
        )

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

        self._advance_search_revision()
        self.add_domain_event(ProductUpdated(**self._snapshot_event_fields()))
        return Result[None].ok(None)

    def activate(self) -> Result[None]:
        if self.is_active:
            return Result[None].fail(CatalogErrors.already_active())

        self.is_active = True
        self._advance_search_revision()
        self.add_domain_event(ProductActivated(**self._snapshot_event_fields()))
        return Result[None].ok(None)

    def deactivate(self) -> Result[None]:
        if not self.is_active:
            return Result[None].fail(CatalogErrors.already_deactivated())

        self.is_active = False
        self._advance_search_revision()
        self.add_domain_event(ProductDeactivated(**self._snapshot_event_fields()))
        return Result[None].ok(None)

    def mark_deleted(self) -> Result[None]:
        """Удаление — не переход состояния агрегата (строка просто исчезает
        из БД, CONTEXT.md «Удаление»), но само событие всё равно должно уйти
        в Outbox — репозиторий вызывает это перед `session.delete()`."""
        self.add_domain_event(ProductDeleted(product_id=self.id))
        return Result[None].ok(None)

    def _advance_search_revision(self) -> None:
        self.search_revision += 1

    def _snapshot_event_fields(self) -> _SnapshotEventFields:
        return {
            "product_id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "price": self.price,
            "is_active": self.is_active,
            "search_revision": self.search_revision,
            "created_at": self.created_at,
        }

import uuid
from collections.abc import Sequence

import pytest

from application.errors import (
    CheckoutQuoteProductHiddenError,
    CheckoutQuoteProductInactiveError,
    CheckoutQuoteProductNotFoundError,
)
from application.ports import Actor, OwnerSnapshot
from application.queries.get_checkout_quote import (
    GetCheckoutQuoteQuery,
    GetCheckoutQuoteQueryHandler,
)
from contracts.checkout_quote import CheckoutQuoteView
from domain.entities.product import Product
from domain.errors import CatalogErrors
from domain.product_image import ProductImage
from domain.repositories import PageInfo, ProductPage
from domain.value_objects.product_id import ProductId

OWNER_ID = uuid.uuid4()
BUYER_ID = uuid.uuid4()


def _product(
    *,
    product_id: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001"),
    price: float = 19.99,
    is_active: bool = True,
) -> Product:
    result = Product.create(
        ProductId.create(product_id),
        name="Товар",
        description="Описание товара",
        price=price,
        category="Категория",
        user_id=OWNER_ID,
    )
    assert result.is_ok
    product = result.value
    if not is_active:
        deactivated = product.deactivate()
        assert deactivated.is_ok
    return product


class FakeProductRepository:
    def __init__(self, product: Product | None = None) -> None:
        self.product = product

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        return self.product if self.product and self.product.id == product_id else None

    async def get_product_image(self, product_id: ProductId) -> ProductImage | None:
        return None

    async def get_product_images_by_ids(
        self, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ProductImage]:
        return {}

    async def list(self, **kwargs: object) -> ProductPage:
        return ProductPage(items=[], page_info=PageInfo(None, None, False, False))


class FakeOwnerReadModel:
    def __init__(self, owner: OwnerSnapshot | None = None) -> None:
        self.owner = owner

    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None:
        return self.owner if self.owner and self.owner.user_id == user_id else None


def _actor() -> Actor:
    return Actor(user_id=BUYER_ID, token="token")


def _query(product_id: uuid.UUID, *, quantity: int) -> GetCheckoutQuoteQuery:
    return GetCheckoutQuoteQuery(
        product_id=product_id, quantity=quantity, actor=_actor()
    )


async def test_returns_quote_for_active_product_with_active_owner() -> None:
    product = _product()
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    result = await handler.execute(_query(product.id.value, quantity=2))

    assert result.is_ok
    assert result.value == CheckoutQuoteView.from_domain(product, quantity=2)


async def test_rejects_zero_quantity_with_a_result_failure() -> None:
    product = _product()
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    result = await handler.execute(_query(product.id.value, quantity=0))

    assert result.is_err
    assert result.error.code == "invalid_quantity"


async def test_rejects_negative_quantity_with_a_result_failure() -> None:
    product = _product()
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    result = await handler.execute(_query(product.id.value, quantity=-1))

    assert result.is_err
    assert result.error.code == "invalid_quantity"


async def test_raises_not_found_when_product_does_not_exist() -> None:
    repo = FakeProductRepository(None)
    owners = FakeOwnerReadModel(None)
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductNotFoundError):
        await handler.execute(_query(uuid.uuid4(), quantity=1))


async def test_raises_not_found_when_product_was_deleted() -> None:
    """Репозиторий возвращает `None` одинаково для «никогда не существовал»
    и «был удалён» (физическое удаление, нет tombstone) — тот же кейс, что
    и «не найден» (issue #366, architect decision brief, риск №2)."""
    repo = FakeProductRepository(None)
    owners = FakeOwnerReadModel(None)
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductNotFoundError):
        await handler.execute(
            _query(uuid.UUID("00000000-0000-0000-0000-000000000099"), quantity=1)
        )


async def test_raises_inactive_when_product_is_deactivated() -> None:
    product = _product(is_active=False)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductInactiveError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_raises_hidden_when_owner_is_deactivated() -> None:
    product = _product(is_active=True)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", False, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductHiddenError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_raises_hidden_when_owner_read_model_has_no_row() -> None:
    """Отсутствующая строка owner-read-модели трактуется как деактивированный
    Владелец (deny-by-default), как и в `GetProductQueryHandler`."""
    product = _product(is_active=True)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(None)
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductHiddenError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_owner_deactivated_takes_precedence_over_product_deactivated() -> None:
    product = _product(is_active=False)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", False, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)

    with pytest.raises(CheckoutQuoteProductHiddenError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_raises_hidden_based_solely_on_eligibility_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Хендлер обязан выбирать ApplicationError только по коду `Error`,
    возвращённого `evaluate_checkout_eligibility` — не пересчитывать
    `owner_is_active` самостоятельно. Здесь `owner_is_active=True` (что,
    при повторной независимой проверке, привело бы к `...InactiveError`),
    но замоканный domain-результат — `checkout_quote_hidden`, поэтому
    единственно верный исход — `CheckoutQuoteProductHiddenError`
    (issue #366, code-review Standards finding)."""
    product = _product(is_active=True)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)
    monkeypatch.setattr(
        "application.queries.get_checkout_quote.evaluate_checkout_eligibility",
        lambda product, *, owner_is_active: CatalogErrors.checkout_quote_hidden(),
    )

    with pytest.raises(CheckoutQuoteProductHiddenError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_raises_inactive_based_solely_on_eligibility_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Зеркальный случай: `owner_is_active=False` (что при независимой
    проверке привело бы к `...HiddenError`), но замоканный domain-результат —
    `checkout_quote_inactive`, поэтому единственно верный исход —
    `CheckoutQuoteProductInactiveError`."""
    product = _product(is_active=True)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", False, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)
    monkeypatch.setattr(
        "application.queries.get_checkout_quote.evaluate_checkout_eligibility",
        lambda product, *, owner_is_active: CatalogErrors.checkout_quote_inactive(),
    )

    with pytest.raises(CheckoutQuoteProductInactiveError):
        await handler.execute(_query(product.id.value, quantity=1))


async def test_owner_gets_no_quote_for_their_own_deactivated_product() -> None:
    """Checkout eligibility строже видимости — даже владелец не получает
    quote на свой деактивированный товар (issue #366, в отличие от
    `GetProductQueryHandler`)."""
    product = _product(is_active=False)
    repo = FakeProductRepository(product)
    owners = FakeOwnerReadModel(OwnerSnapshot(OWNER_ID, "user", True, 1))
    handler = GetCheckoutQuoteQueryHandler(repo, owners)
    owner_actor_query = GetCheckoutQuoteQuery(
        product_id=product.id.value,
        quantity=1,
        actor=Actor(user_id=OWNER_ID, token="token"),
    )

    with pytest.raises(CheckoutQuoteProductInactiveError):
        await handler.execute(owner_actor_query)

import uuid

import pytest
from kernel_domain.errors import ErrorType

from domain.entities.product import Product
from domain.events import (
    ProductActivated,
    ProductCreated,
    ProductDeactivated,
    ProductDeleted,
    ProductUpdated,
)
from domain.value_objects.product_id import ProductId


def test_product_id_new_id_returns_a_uuid() -> None:
    product_id = ProductId.new_id()

    assert isinstance(product_id.value, uuid.UUID)


def test_product_id_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        ProductId(uuid.uuid4())


def _create(**overrides: object) -> Product:
    defaults: dict[str, object] = {
        "name": "Название товара",
        "description": "Описание",
        "price": 10.0,
        "category": "Категория",
        "user_id": uuid.uuid4(),
    }
    defaults.update(overrides)
    result = Product.create(ProductId.new_id(), **defaults)  # type: ignore[arg-type]
    assert result.is_ok
    product = result.value
    # ProductCreated проверяется отдельным тестом, здесь очищаем его.
    product.pull_events()
    return product


def test_create_raises_product_created_with_expected_fields() -> None:
    owner_id = uuid.uuid4()
    result = Product.create(
        ProductId.new_id(),
        name="Название товара",
        description="Описание",
        price=10.0,
        category="Категория",
        user_id=owner_id,
    )

    assert result.is_ok
    product = result.value
    assert product.is_active is True

    [event] = product.pull_events()
    assert isinstance(event, ProductCreated)
    assert event.product_id.value == product.id.value
    assert event.user_id == owner_id
    assert event.name == "Название товара"
    assert event.category == "Категория"
    assert event.price == 10.0


def test_create_rejects_too_short_name() -> None:
    result = Product.create(
        ProductId.new_id(),
        name="ab",
        description="",
        price=10.0,
        category="Категория",
        user_id=uuid.uuid4(),
    )

    assert result.is_err
    assert result.error.type is ErrorType.VALIDATION
    assert result.error.code == "invalid_name"


def test_create_rejects_negative_price() -> None:
    result = Product.create(
        ProductId.new_id(),
        name="Название товара",
        description="",
        price=-1.0,
        category="Категория",
        user_id=uuid.uuid4(),
    )

    assert result.is_err
    assert result.error.code == "invalid_price"


def test_update_changes_only_provided_fields() -> None:
    product = _create()
    original_category = product.category

    result = product.update(name="Новое имя")

    assert result.is_ok
    assert product.name == "Новое имя"
    assert product.category == original_category

    [event] = product.pull_events()
    assert isinstance(event, ProductUpdated)
    assert event.product_id == product.id


def test_update_rejects_invalid_value_without_mutating_state() -> None:
    product = _create()
    original_name = product.name

    result = product.update(name="ab")

    assert result.is_err
    assert result.error.code == "invalid_name"
    assert product.name == original_name
    assert product.pull_events() == []


def test_activate_deactivate_toggle_and_raise_events() -> None:
    product = _create()

    deactivate_result = product.deactivate()
    assert deactivate_result.is_ok
    assert product.is_active is False

    activate_result = product.activate()
    assert activate_result.is_ok
    assert product.is_active is True

    deactivated_event, activated_event = product.pull_events()
    assert isinstance(deactivated_event, ProductDeactivated)
    assert isinstance(activated_event, ProductActivated)
    assert deactivated_event.product_id == product.id
    assert activated_event.product_id == product.id


def test_activate_already_active_product_fails() -> None:
    product = _create()

    result = product.activate()

    assert result.is_err
    assert result.error.type is ErrorType.CONFLICT
    assert result.error.code == "already_active"


def test_deactivate_already_deactivated_product_fails() -> None:
    product = _create()
    product.deactivate()

    result = product.deactivate()

    assert result.is_err
    assert result.error.code == "already_deactivated"


def test_mark_deleted_raises_product_deleted_event() -> None:
    product = _create()

    result = product.mark_deleted()

    assert result.is_ok
    [event] = product.pull_events()
    assert isinstance(event, ProductDeleted)
    assert event.product_id == product.id


def test_product_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        Product(
            ProductId.new_id(),
            name="Название товара",
            description="Описание",
            price=10.0,
            category="Категория",
            user_id=uuid.uuid4(),
            is_active=True,
        )

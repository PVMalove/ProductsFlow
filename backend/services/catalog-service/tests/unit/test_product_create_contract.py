import uuid

from api.schemas import ProductCreateRequest
from application.commands import CreateProductCommand
from application.ports import Actor
from contracts.product import ProductView
from domain.entities.product import Product
from domain.value_objects.product_id import ProductId


def test_product_create_request_to_command_carries_the_actor_and_body_fields() -> None:
    actor = Actor(user_id=uuid.uuid4(), token="token")
    request = ProductCreateRequest(
        name="Товар", description="Описание", price=9.99, category="Категория"
    )

    command = request.to_command(actor=actor)

    assert command == CreateProductCommand(
        actor=actor,
        name="Товар",
        description="Описание",
        price=9.99,
        category="Категория",
    )


def test_product_view_from_domain_mirrors_the_product_fields() -> None:
    user_id = uuid.uuid4()
    result = Product.create(
        ProductId.new_id(),
        name="Товар",
        description="Описание",
        price=9.99,
        category="Категория",
        user_id=user_id,
    )
    assert result.is_ok
    product = result.value

    view = ProductView.from_domain(product)

    assert view == ProductView(
        id=product.id.value,
        name="Товар",
        description="Описание",
        price=9.99,
        category="Категория",
        user_id=user_id,
        is_active=True,
    )

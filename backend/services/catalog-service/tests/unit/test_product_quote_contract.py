import uuid

from api.schemas import ProductQuoteRequest
from application.ports import Actor
from application.queries import GetCheckoutQuoteQuery


def test_product_quote_request_to_query_carries_path_id_quantity_and_actor() -> None:
    actor = Actor(user_id=uuid.uuid4(), token="token")
    product_id = uuid.uuid4()
    request = ProductQuoteRequest(product_id=product_id, quantity=3)

    query = request.to_query(actor=actor)

    assert query == GetCheckoutQuoteQuery(
        product_id=product_id, quantity=3, actor=actor
    )


def test_product_quote_request_carries_non_positive_quantity_unvalidated() -> None:
    """`quantity`-валидация доменная (`CatalogErrors.invalid_quantity`), не
    Pydantic-уровня — схема не отклоняет `0`/отрицательные значения (issue
    #366)."""
    actor = Actor(user_id=uuid.uuid4(), token="token")
    product_id = uuid.uuid4()
    request = ProductQuoteRequest(product_id=product_id, quantity=-1)

    query = request.to_query(actor=actor)

    assert query.quantity == -1

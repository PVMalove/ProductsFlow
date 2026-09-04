import uuid

from api.schemas import ProductGetRequest
from application.ports import Actor
from application.queries import GetProductQuery


def test_product_target_request_to_query_carries_path_id_and_actor() -> None:
    actor = Actor(user_id=uuid.uuid4(), token="token")
    product_id = uuid.uuid4()
    request = ProductGetRequest(product_id=product_id)

    query = request.to_query(actor=actor)

    assert query == GetProductQuery(product_id=product_id, actor=actor)


def test_product_target_request_to_query_allows_anonymous_actor() -> None:
    product_id = uuid.uuid4()
    request = ProductGetRequest(product_id=product_id)

    query = request.to_query(actor=None)

    assert query == GetProductQuery(product_id=product_id, actor=None)

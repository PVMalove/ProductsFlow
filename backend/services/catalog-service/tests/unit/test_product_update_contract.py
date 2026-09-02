import uuid

from api.schemas import ProductUpdateRequest
from application.commands import UpdateProductCommand
from application.ports import Actor


def test_product_update_request_to_command_carries_path_id_and_actor() -> None:
    actor = Actor(user_id=uuid.uuid4(), token="token")
    product_id = uuid.uuid4()
    request = ProductUpdateRequest(price=42.0)

    command = request.to_command(product_id=product_id, actor=actor)

    assert command == UpdateProductCommand(
        product_id=product_id, actor=actor, price=42.0
    )

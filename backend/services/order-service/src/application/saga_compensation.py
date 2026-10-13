"""Общие шаги компенсации Saga для command-handler'ов order (issue #377)."""

from domain.entities.order import Order
from domain.repositories import SagaCommandOutboxRepository


async def void_stored_authorization(
    order: Order, outbox: SagaCommandOutboxRepository
) -> None:
    """Ставит intent `payment.void.v1` для авторизации, сохранённой в Order
    (в том числе только что записанной `record_late_authorization`); без
    авторизации — ничего."""
    if order.payment_authorization_id is not None:
        await outbox.enqueue_void(
            order_id=order.id, authorization_id=order.payment_authorization_id
        )

"""Inbox-гейт order-worker'а по producer'у (issue #375, D4).

`message_id` входящих событий — BigInt sequence generic outbox'а КАЖДОГО
producer'а (inventory-service, payment-service); обе sequence стартуют с 1,
поэтому ключ дедупликации — пара `(source, message_id)`, не один
`message_id`."""

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.entity_configurations.models import ProcessedMessageModel

INVENTORY_SOURCE = "inventory"
PAYMENT_SOURCE = "payment"


def parse_outbox_message_id(message: AbstractIncomingMessage) -> int:
    # События едут через generic `kernel_platform` outbox producer'а — тот же
    # BigInt `message_id`, что inventory-worker's `ProcessedMessage`-гейт
    # (issue #367, находка 3) ожидает от чужого доменного события.
    raw_message_id = message.message_id
    try:
        message_id = int(raw_message_id) if raw_message_id is not None else 0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}") from exc
    if message_id <= 0:
        raise ValueError(f"Invalid outbox message id: {raw_message_id!r}")
    return message_id


async def claim_message(session: AsyncSession, *, source: str, message_id: int) -> bool:
    """`True`, если сообщение впервые захвачено этой транзакцией; `False` —
    уже обработано (повторная доставка)."""
    claimed_message_id = await session.scalar(
        insert(ProcessedMessageModel)
        .values(source=source, message_id=message_id)
        .on_conflict_do_nothing()
        .returning(ProcessedMessageModel.message_id)
    )
    return claimed_message_id is not None

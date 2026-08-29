import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import aio_pika.exceptions
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractExchange
from aiormq.exceptions import DeliveryError
from pamqp.commands import Basic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kernel_platform.outbox.models import OutboxMessage

logger = logging.getLogger(__name__)

EVENTS_EXCHANGE_NAME = "productsflow.events"

DEFAULT_BATCH_SIZE = 50
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 5.0


def build_message(row: OutboxMessage) -> Message:
    """Собирает AMQP-сообщение из строки outbox (находки #64 §1.7): без явного
    `message_id` `aio-pika` подставил бы случайный UUID на каждой отправке
    (ломает дедупликацию у консьюмера), без явного `delivery_mode` сообщение
    ушло бы как `NOT_PERSISTENT` (дефолт `aio-pika`).
    """
    return Message(
        body=json.dumps(row.payload).encode(),
        message_id=str(row.id),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        timestamp=row.occurred_at,
        type=row.event_type,
        headers={"traceparent": row.trace_context},
    )


class OutboxPublisher:
    """Один цикл Outbox Publisher (ADR 0014): выбрать неопубликованные строки,
    опубликовать через `aio-pika` с publisher confirms, проставить
    `published_at` только при `isinstance(result, Basic.Ack)`.

    Happy path (issue #100) — без `SELECT ... FOR UPDATE SKIP LOCKED`,
    backoff по `attempts`/`next_attempt_at` и восстановления после краша
    (issue #101, следующий тикет): при любом исходе публикации, отличном от
    `Basic.Ack`, строка просто остаётся неопубликованной и будет
    предпринята заново на следующем цикле — без счётчика попыток.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        exchange: AbstractExchange,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        publish_timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._exchange = exchange
        self._batch_size = batch_size
        self._publish_timeout_seconds = publish_timeout_seconds

    async def run_once(self) -> None:
        async with self._session_factory() as session:
            for row in await self._select_unpublished(session):
                await self._publish_row(session, row)

    async def _select_unpublished(
        self, session: AsyncSession
    ) -> Sequence[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.published_at.is_(None))
            .order_by(OutboxMessage.id)
            .limit(self._batch_size)
        )
        return (await session.scalars(stmt)).all()

    async def _publish_row(self, session: AsyncSession, row: OutboxMessage) -> None:
        try:
            confirmation = await self._exchange.publish(
                build_message(row),
                routing_key=row.event_type,
                mandatory=True,
                timeout=self._publish_timeout_seconds,
            )
        except (
            DeliveryError,
            aio_pika.exceptions.AMQPError,
            TimeoutError,
            ConnectionError,
        ):
            # DeliveryError — брокер отказал (nack) или сообщение
            # неотмаршрутизировано с on_return_raises=True; остальные —
            # обрыв соединения/канала или истёкший timeout. Оба класса
            # исходов в happy path одинаковы: строка остаётся
            # неопубликованной, следующий цикл попробует снова.
            logger.warning(
                "Outbox row %s: публикация не подтверждена брокером",
                row.id,
                exc_info=True,
            )
            return

        if not isinstance(confirmation, Basic.Ack):
            # None (confirms выключены) или ReturnedMessage (нет биндинга,
            # mandatory=True, on_return_raises=False) — не исключение, но и
            # не подтверждение доставки (находки #64 §1.3).
            logger.warning(
                "Outbox row %s: брокер не прислал Ack (%r)", row.id, confirmation
            )
            return

        row.published_at = datetime.now(UTC)
        await session.commit()

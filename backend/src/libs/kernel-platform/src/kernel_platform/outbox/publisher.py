import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import aio_pika.exceptions
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractExchange
from aiormq.exceptions import DeliveryError
from pamqp.commands import Basic
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kernel_platform.outbox.models import OutboxMessage

logger = logging.getLogger(__name__)

EVENTS_EXCHANGE_NAME = "productsflow.events"

DEFAULT_BATCH_SIZE = 50
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 5.0

# Тюнинг-параметр (ADR 0014 сознательно не фиксирует базу/потолок): 1с, 2с,
# 4с, ... до потолка в 5 минут.
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CEILING_SECONDS = 300.0

# Publisher без give-up (ADR 0014) => attempts растёт неограниченно при
# долгом простое брокера. 2**64 уже на много порядков больше любого
# разумного потолка, поэтому дальнейший рост показателя ничего не меняет в
# результате min(), но без этой отсечки сам 2**(attempts-1) как int
# переполнил бы float при конвертации.
_MAX_BACKOFF_EXPONENT = 64


def compute_backoff(attempts: int) -> timedelta:
    """Экспоненциальный backoff с потолком, без give-up (ADR 0014): `attempts`
    — счётчик уже после инкремента текущего отказа, поэтому первый отказ
    (attempts=1) откладывает повтор на `BACKOFF_BASE_SECONDS`.
    """
    exponent = min(attempts - 1, _MAX_BACKOFF_EXPONENT)
    seconds = min(BACKOFF_BASE_SECONDS * 2**exponent, BACKOFF_CEILING_SECONDS)
    return timedelta(seconds=seconds)


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
    """Один цикл Outbox Publisher (ADR 0014): выбрать неопубликованные строки
    через `SELECT ... FOR UPDATE SKIP LOCKED` (безопасно при нескольких
    параллельных инстансах воркера), опубликовать через `aio-pika` с
    publisher confirms, проставить `published_at` только при
    `isinstance(result, Basic.Ack)`.

    Строки одного батча выбираются и коммитятся в рамках одной транзакции —
    блокировка держится на весь цикл `run_once`, а не только на первую
    строку, иначе коммит по первой же строке снял бы `FOR UPDATE`-блокировку
    с ещё не обработанных строк того же батча. Если процесс падает после
    `claim` (SELECT ... FOR UPDATE), но до коммита — транзакция не
    коммитится, блокировка снимается вместе с обрывом соединения к
    Postgres, и строка остаётся `published_at IS NULL` для следующего
    цикла/инстанса (issue #101, тест kill-restart). Любой исход, отличный
    от `Basic.Ack` (nack, unroutable, timeout, обрыв соединения),
    инкрементирует `attempts` и откладывает следующую попытку через
    экспоненциальный backoff без give-up — строка никогда не помечается
    как «сдавшаяся».
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
                await self._publish_row(row)
            await session.commit()

    async def _select_unpublished(
        self, session: AsyncSession
    ) -> Sequence[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.published_at.is_(None),
                or_(
                    OutboxMessage.next_attempt_at.is_(None),
                    OutboxMessage.next_attempt_at <= func.now(),
                ),
            )
            .order_by(OutboxMessage.id)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        return (await session.scalars(stmt)).all()

    async def _publish_row(self, row: OutboxMessage) -> None:
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
            # обрыв соединения/канала или истёкший timeout.
            logger.warning(
                "Outbox row %s: публикация не подтверждена брокером",
                row.id,
                exc_info=True,
            )
            self._record_failure(row)
            return

        if not isinstance(confirmation, Basic.Ack):
            # None (confirms выключены) или ReturnedMessage (нет биндинга,
            # mandatory=True, on_return_raises=False) — не исключение, но и
            # не подтверждение доставки (находки #64 §1.3).
            logger.warning(
                "Outbox row %s: брокер не прислал Ack (%r)", row.id, confirmation
            )
            self._record_failure(row)
            return

        row.published_at = datetime.now(UTC)

    def _record_failure(self, row: OutboxMessage) -> None:
        row.attempts += 1
        row.next_attempt_at = datetime.now(UTC) + compute_backoff(row.attempts)

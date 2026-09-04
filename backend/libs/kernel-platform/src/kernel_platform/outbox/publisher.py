# ruff: noqa: E501
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
from kernel_platform.outbox.settings import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CEILING_SECONDS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_PUBLISH_TIMEOUT_SECONDS,
    MAX_BACKOFF_EXPONENT,
)

logger = logging.getLogger(__name__)


def compute_backoff(attempts: int) -> timedelta:
    """Вычисляет величину задержки (backoff) по номеру попытки (экспоненциально).

    Задержка растет по степени двойки от `BACKOFF_BASE_SECONDS`, но не превышает `BACKOFF_CEILING_SECONDS`.
    Защищено от переполнения интов жестким лимитом степени.

    Args:
        attempts (int): Текущее количество неудачных попыток (начиная с 1).

    Returns:
        timedelta: Рассчитанный интервал времени до следующей попытки."""
    exponent = min(attempts - 1, MAX_BACKOFF_EXPONENT)
    seconds = min(BACKOFF_BASE_SECONDS * 2**exponent, BACKOFF_CEILING_SECONDS)
    return timedelta(seconds=seconds)


def build_message(row: OutboxMessage) -> Message:
    """Пакует ORM-модель Outbox-сообщения в сырое AMQP сообщение `aio-pika`.

    Форсирует `message_id` из базы для дедупликации, выставляет `DeliveryMode.PERSISTENT` для надежности.

    Args:
        row (OutboxMessage): Запись из таблички аутбокса.

    Returns:
        Message: Сформированное сообщение для брокера."""
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
    """Один цикл Outbox Publisher : выбрать неопубликованные строки
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
    цикла/инстанса. Любой исход, отличный
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
        """Инициализирует паблишер аутбокса.

        Args:
            session_factory: Фабрика асинхронных сессий алхимии.
            exchange (AbstractExchange): Куда кидаем события.
            batch_size (int): Размер пачки при фетче из базы.
            publish_timeout_seconds (float): Таймаут на ack от брокера."""
        self._session_factory = session_factory
        self._exchange = exchange
        self._batch_size = batch_size
        self._publish_timeout_seconds = publish_timeout_seconds

    async def run_once(self) -> None:
        """Прокручивает один цикл транзакционного аутбокса.

        Берет сессию, фетчит пачку строк под `FOR UPDATE SKIP LOCKED`. Пытается отправить их в RabbitMQ.
        Если брокер подтверждает доставку (Ack), строки помечаются опубликованными.
        Весь батч коммитится в одной транзакции."""
        async with self._session_factory() as session:
            for row in await self._select_unpublished(session):
                await self._publish_row(row)
            await session.commit()

    async def _select_unpublished(
        self, session: AsyncSession
    ) -> Sequence[OutboxMessage]:
        """Фетчит недоставленные записи с локом.

        Делает `SELECT ... FOR UPDATE SKIP LOCKED` с лимитом `batch_size`. Ищет строки без `published_at`,
        у которых либо `next_attempt_at` еще не настал, либо его нет.

        Args:
            session (AsyncSession): Открытая сессия к БД.

        Returns:
            Sequence[OutboxMessage]: Пачка строк для публикации."""
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
        """Публикует одну запись в RabbitMQ и хэндлит результат.

        В случае успешного `Basic.Ack` — сетапит `published_at`. В случае Nack,
        сетевой ошибки, таймаута или Unroutable (при mandatory=True) — инкрементит счетчик попыток через `_record_failure`.

        Args:
            row (OutboxMessage): Строка аутбокса."""
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
            logger.warning(
                "Outbox row %s: публикация не подтверждена брокером",
                row.id,
                exc_info=True,
            )
            self._record_failure(row)
            return
        if not isinstance(confirmation, Basic.Ack):
            logger.warning(
                "Outbox row %s: брокер не прислал Ack (%r)", row.id, confirmation
            )
            self._record_failure(row)
            return
        row.published_at = datetime.now(UTC)

    def _record_failure(self, row: OutboxMessage) -> None:
        """Шедулит ретрай на случай сбоя публикации.

        Инкрементит `attempts` и высчитывает `next_attempt_at` через `compute_backoff`.

        Args:
            row (OutboxMessage): Модель, которую не удалось отправить."""
        row.attempts += 1
        row.next_attempt_at = datetime.now(UTC) + compute_backoff(row.attempts)

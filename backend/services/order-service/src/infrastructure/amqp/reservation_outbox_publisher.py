# ruff: noqa: E501
"""Дренаж/публикация `reservation_outbox` (issue #372, D6) — тот же
`FOR UPDATE SKIP LOCKED`/backoff идиом, что `kernel_platform.outbox.publisher
.OutboxPublisher`, но публикует `Command` (`inventory.reserve.v1`) через
`kernel_platform.commands.publish_command`, не доменное событие: собственная
таблица `reservation_outbox` (UUID PK, годится напрямую как
`Command.command_id` — находка 5, `OutboxMessage`'s BigInt PK несовместим)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aio_pika.exceptions
from aio_pika.abc import AbstractExchange
from aiormq.exceptions import DeliveryError
from kernel_platform.commands import Command, publish_command
from pamqp.commands import Basic
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.db.entity_configurations.models import ReservationOutboxModel

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CEILING_SECONDS = 60.0
_MAX_BACKOFF_EXPONENT = 5
_DEFAULT_BATCH_SIZE = 20
_DEFAULT_PUBLISH_TIMEOUT_SECONDS = 5.0
COMMAND_TYPE = "inventory.reserve.v1"


def compute_backoff(attempts: int) -> timedelta:
    exponent = min(attempts - 1, _MAX_BACKOFF_EXPONENT)
    seconds = min(_BACKOFF_BASE_SECONDS * 2**exponent, _BACKOFF_CEILING_SECONDS)
    return timedelta(seconds=seconds)


def build_command(row: ReservationOutboxModel) -> Command:
    payload: dict[str, Any] = row.payload
    return Command(
        command_id=row.id,
        command_type=COMMAND_TYPE,
        # Единственная причина исходящей команды — создание этого Order
        # (finding 8) — command_id самой команды годится как causation_id.
        causation_id=row.id,
        correlation_id=str(row.order_id),
        payload=payload,
    )


class ReservationOutboxPublisher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        exchange: AbstractExchange,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        publish_timeout_seconds: float = _DEFAULT_PUBLISH_TIMEOUT_SECONDS,
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
    ) -> list[ReservationOutboxModel]:
        stmt = (
            select(ReservationOutboxModel)
            .where(
                ReservationOutboxModel.published_at.is_(None),
                or_(
                    ReservationOutboxModel.next_attempt_at.is_(None),
                    ReservationOutboxModel.next_attempt_at <= func.now(),
                ),
            )
            .order_by(ReservationOutboxModel.id)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        return list((await session.scalars(stmt)).all())

    async def _publish_row(self, row: ReservationOutboxModel) -> None:
        try:
            confirmation = await publish_command(
                self._exchange,
                build_command(row),
                timeout_seconds=self._publish_timeout_seconds,
            )
        except (
            DeliveryError,
            aio_pika.exceptions.AMQPError,
            TimeoutError,
            ConnectionError,
        ):
            logger.warning(
                "reservation_outbox row %s: публикация не подтверждена брокером",
                row.id,
                exc_info=True,
            )
            self._record_failure(row)
            return
        if not isinstance(confirmation, Basic.Ack):
            logger.warning(
                "reservation_outbox row %s: брокер не прислал Ack (%r)",
                row.id,
                confirmation,
            )
            self._record_failure(row)
            return
        row.published_at = datetime.now(UTC)

    def _record_failure(self, row: ReservationOutboxModel) -> None:
        row.attempts += 1
        row.next_attempt_at = datetime.now(UTC) + compute_backoff(row.attempts)

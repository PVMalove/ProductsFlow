# ruff: noqa: E501
"""order-worker (issue #372, D8) — первый долгоживущий процесс order-service,
двумя параллельными задачами (`asyncio.gather`, каждая со своей сессией —
Risk 2 архитектурного брифа): (1) event-consumer `inventory.reserved.v1`
(D7); (2) периодический дренаж `reservation_outbox` -> `inventory.reserve.v1`
(D6). Отдельный от `api/main.py`'s HTTP-процесса — HTTP не должен блокироваться
на AMQP-consume loop (находка 1). issue #375, D7: второй consumer — результаты
`payment.authorize.v1` из очереди `order.payment-events`. issue #376, D7: та же
очередь получает `payment.captured.v1`, inventory-очередь —
`inventory.allocated.v1`; второй drain loop публикует доменные события
(`order.completed.v1`) из общего `outbox_messages` в `productsflow.events`."""

import asyncio
import logging

import aio_pika
from aio_pika import ExchangeType
from kernel_platform.consumer import consume
from kernel_platform.outbox.publisher import OutboxPublisher
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from kernel_platform.topology import (
    COMMANDS_EXCHANGE_NAME,
    declare_command_topology,
    declare_topology,
)
from observability.tracing import configure_tracing
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.workers.commands.authorization_result_handler import (
    PAYMENT_EVENT_TYPES,
    build_authorization_result_handler,
)
from api.workers.commands.authorization_result_handler import (
    QUEUE_NAME as PAYMENT_EVENTS_QUEUE_NAME,
)
from api.workers.commands.reservation_result_handler import (
    INVENTORY_EVENT_TYPES,
    QUEUE_NAME,
    build_reservation_result_handler,
)
from core.settings import settings
from infrastructure.amqp.reservation_outbox_publisher import ReservationOutboxPublisher
from infrastructure.db.reservation_outbox_repository import COMMAND_TYPES

logger = logging.getLogger(__name__)


async def _drain_loop(
    publisher: ReservationOutboxPublisher | OutboxPublisher, name: str
) -> None:
    while True:
        try:
            await publisher.run_once()
        except Exception:
            logger.exception("order-worker: %s drain failed", name)
        await asyncio.sleep(settings.order_outbox_poll_interval_seconds)


async def main() -> None:
    configure_tracing("order-worker")
    engine = create_async_engine(
        settings.order_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.order_amqp_url)

    try:
        async with connection:
            channel = await connection.channel()

            queue = await declare_topology(
                channel,
                service_name="order",
                queue_name=QUEUE_NAME,
                routing_keys=INVENTORY_EVENT_TYPES,
            )
            await consume(
                queue,
                build_reservation_result_handler(
                    session_factory, settings.order_payment_method_token
                ),
                prefetch_count=1,
            )
            logger.info("order-worker: inventory-event consumer started")

            # issue #375, D7: собственная очередь результатов авторизации —
            # отдельные retry/DLQ-очереди от inventory-событий.
            payment_queue = await declare_topology(
                channel,
                service_name="order",
                queue_name=PAYMENT_EVENTS_QUEUE_NAME,
                routing_keys=PAYMENT_EVENT_TYPES,
            )
            await consume(
                payment_queue,
                build_authorization_result_handler(session_factory),
                prefetch_count=1,
            )
            logger.info("order-worker: authorization-result consumer started")

            # finding 9: order-worker сам объявляет топологию каждой команды
            # перед публикацией — не полагается на то, что inventory-worker/
            # payment-worker гарантированно стартовали первыми.
            for command_type in COMMAND_TYPES:
                await declare_command_topology(channel, command_type)
            commands_exchange = await channel.declare_exchange(
                COMMANDS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
            )
            publisher = ReservationOutboxPublisher(session_factory, commands_exchange)
            logger.info("order-worker: reservation_outbox publisher started")

            # issue #376, D6/D7: доменные события Order (`order.completed.v1`)
            # — generic transactional outbox, тот же `OutboxPublisher`, что у
            # остальных producer'ов, в отдельном poll-цикле.
            events_exchange = await channel.declare_exchange(
                EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
            )
            event_publisher = OutboxPublisher(session_factory, events_exchange)
            logger.info("order-worker: outbox_messages publisher started")

            await asyncio.gather(
                asyncio.Future(),
                _drain_loop(publisher, "reservation_outbox"),
                _drain_loop(event_publisher, "outbox_messages"),
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

# ruff: noqa: E501
"""order-worker (issue #372, D8) — первый долгоживущий процесс order-service,
двумя параллельными задачами (`asyncio.gather`, каждая со своей сессией —
Risk 2 архитектурного брифа): (1) event-consumer `inventory.reserved.v1`
(D7); (2) периодический дренаж `reservation_outbox` -> `inventory.reserve.v1`
(D6). Отдельный от `api/main.py`'s HTTP-процесса — HTTP не должен блокироваться
на AMQP-consume loop (находка 1)."""

import asyncio
import logging

import aio_pika
from aio_pika import ExchangeType
from kernel_platform.consumer import consume
from kernel_platform.topology import (
    COMMANDS_EXCHANGE_NAME,
    declare_command_topology,
    declare_topology,
)
from observability.tracing import configure_tracing
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.workers.commands.reservation_result_handler import (
    QUEUE_NAME,
    RESERVED_EVENT_TYPE,
    build_reservation_result_handler,
)
from core.settings import settings
from infrastructure.amqp.reservation_outbox_publisher import (
    COMMAND_TYPE,
    ReservationOutboxPublisher,
)

logger = logging.getLogger(__name__)


async def _drain_loop(publisher: ReservationOutboxPublisher) -> None:
    while True:
        try:
            await publisher.run_once()
        except Exception:
            logger.exception("order-worker: reservation_outbox drain failed")
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
                routing_keys=(RESERVED_EVENT_TYPE,),
            )
            await consume(
                queue,
                build_reservation_result_handler(session_factory),
                prefetch_count=1,
            )
            logger.info("order-worker: reservation-result consumer started")

            # finding 9: order-worker сам объявляет топологию команды перед
            # публикацией — не полагается на то, что inventory-worker
            # гарантированно стартовал первым.
            await declare_command_topology(channel, COMMAND_TYPE)
            commands_exchange = await channel.declare_exchange(
                COMMANDS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
            )
            publisher = ReservationOutboxPublisher(session_factory, commands_exchange)
            logger.info("order-worker: reservation_outbox publisher started")

            await asyncio.gather(asyncio.Future(), _drain_loop(publisher))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

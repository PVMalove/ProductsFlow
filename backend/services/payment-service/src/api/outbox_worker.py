import asyncio
import logging

import aio_pika
from kernel_platform.outbox.listener import OutboxListener, to_asyncpg_dsn
from kernel_platform.outbox.publisher import OutboxPublisher
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from observability.tracing import configure_tracing
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.settings import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """Publishes payment-service's transactional-outbox rows to RabbitMQ.

    `payment.authorized.v1`/`payment.authorization_declined.v1`/
    `payment.authorization_timed_out.v1`/`payment.voided.v1`, issue #371.
    Дословное зеркало inventory-service's outbox_worker.py — тот же generic
    `OutboxPublisher`, без изменений в самом паблишере."""
    configure_tracing("payment-outbox-worker")
    engine = create_async_engine(
        settings.payment_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.payment_amqp_url)
    try:
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
            )
            publisher = OutboxPublisher(session_factory, exchange)
            listener_dsn = to_asyncpg_dsn(settings.payment_database_url)
            async with OutboxListener(listener_dsn) as listener:
                logger.info("payment-outbox-worker: publisher started")
                while True:
                    try:
                        await publisher.run_once()
                        await listener.wait_for_wakeup(
                            settings.payment_outbox_poll_interval_seconds
                        )
                    except Exception:
                        logger.exception("payment-outbox-worker: publisher loop failed")
                        await asyncio.sleep(
                            settings.payment_outbox_poll_interval_seconds
                        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

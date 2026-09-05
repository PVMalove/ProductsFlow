import asyncio
import logging

import aio_pika
from kernel_platform.outbox.listener import OutboxListener, to_asyncpg_dsn
from kernel_platform.outbox.publisher import OutboxPublisher
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.search_worker import declare_product_search_queue
from core.settings import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """Publishes Catalog's transactional-outbox rows to RabbitMQ."""
    engine = create_async_engine(
        settings.catalog_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    connection = await aio_pika.connect_robust(settings.catalog_amqp_url)
    try:
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
            )
            # The publisher owns the transport topology for Product snapshots so
            # a cold start cannot return a snapshot before the consumer process
            # gets its chance to declare the durable queue.
            await declare_product_search_queue(channel)
            publisher = OutboxPublisher(session_factory, exchange)
            listener_dsn = to_asyncpg_dsn(settings.catalog_database_url)
            async with OutboxListener(listener_dsn) as listener:
                logger.info("catalog-outbox-worker: publisher started")
                while True:
                    try:
                        await publisher.run_once()
                        await listener.wait_for_wakeup(
                            settings.catalog_outbox_poll_interval_seconds
                        )
                    except Exception:
                        logger.exception("catalog-outbox-worker: publisher loop failed")
                        await asyncio.sleep(
                            settings.catalog_outbox_poll_interval_seconds
                        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

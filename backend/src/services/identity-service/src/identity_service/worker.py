import asyncio
import logging

import aio_pika
from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME, OutboxPublisher
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from identity_service.settings import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """identity-worker (ADR 0010): вторая точка входа identity-service, не
    HTTP-процесс — гоняет `OutboxPublisher` на fixed-interval таймере
    (issue #100, happy path; `LISTEN/NOTIFY` — issue #102).
    """
    engine = create_async_engine(settings.identity_database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    connection = await aio_pika.connect_robust(settings.identity_amqp_url)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        publisher = OutboxPublisher(session_factory, exchange)

        logger.info("identity-worker: outbox publisher started")
        while True:
            await publisher.run_once()
            await asyncio.sleep(settings.identity_outbox_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())

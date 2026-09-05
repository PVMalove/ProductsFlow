import asyncio
import logging

import aio_pika
from kernel_platform.outbox.listener import OutboxListener, to_asyncpg_dsn
from kernel_platform.outbox.publisher import OutboxPublisher
from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.settings import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """identity-worker (ADR 0010): вторая точка входа identity-service, не
    HTTP-процесс — гоняет `OutboxPublisher` на гибридном пробуждении (ADR
    0010): `NOTIFY` через `OutboxListener` даёт почти мгновенную реакцию
    (issue #102), 5-секундный poll (issue #100, happy path) остаётся
    страховкой на случай потерянного `NOTIFY`.
    """
    engine = create_async_engine(
        settings.identity_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    connection = await aio_pika.connect_robust(settings.identity_amqp_url)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        publisher = OutboxPublisher(session_factory, exchange)

        listener_dsn = to_asyncpg_dsn(settings.identity_database_url)
        async with OutboxListener(listener_dsn) as listener:
            logger.info("identity-worker: outbox publisher started (hybrid wakeup)")
            while True:
                try:
                    await publisher.run_once()
                except Exception:
                    logger.exception("identity-worker: error in publisher loop")
                    await asyncio.sleep(settings.identity_outbox_poll_interval_seconds)
                    continue

                try:
                    await listener.wait_for_wakeup(
                        settings.identity_outbox_poll_interval_seconds
                    )
                except Exception:
                    logger.exception("identity-worker: error in wakeup loop")
                    await asyncio.sleep(settings.identity_outbox_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging

import aio_pika
from kernel_platform.commands import consume_command
from kernel_platform.topology import declare_command_topology
from observability.tracing import configure_tracing
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.payment_commands import COMMAND_HANDLERS
from core.psp import build_psp_client
from core.settings import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """Запускает payment-worker: authorize/void command-консьюмеры (issue
    #371) — payment-service ничего не консьюмит, кроме своих двух команд, в
    отличие от inventory-worker (нет Product-lifecycle части)."""
    configure_tracing("payment-worker")
    # Fail-fast под APP_ENV=prod (issue #368, архитектурный бриф D5) — тот же
    # гейт, что payment-api's lifespan, теперь и для воркера.
    build_psp_client(settings)
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
            for command_type, handler in COMMAND_HANDLERS.items():
                queue = await declare_command_topology(channel, command_type)
                await consume_command(queue, session_factory, handler)
            logger.info("payment-worker: command consumers started")

            await asyncio.Future()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

# ruff: noqa: E501
from collections.abc import Mapping

from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractQueue

from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME

DLX_EXCHANGE_NAME = "productsflow.dlx"
RETRY_STAGE_TTL_MS = {"retry.5s": 5000, "retry.30s": 30000, "retry.2m": 120000}


async def declare_topology(
    channel: AbstractChannel,
    service_name: str,
    *,
    retry_stage_ttl_ms: Mapping[str, int] | None = None,
) -> AbstractQueue:
    """Идемпотентно объявляет топологию консьюмера с DLX и retry-ступенями.

    Создает quorum-очередь, биндит ее к эксчейнджу событий и сетапит три TTL-очереди для retry-лестницы.
    Для ступеней настраивается статический дед-леттеринг обратно в основную очередь.
    Вызовы `aio-pika.declare_*` идемпотентны, так что при рестарте дубли не плодятся.

    Args:
        channel (AbstractChannel): Открытый AMQP канал.
        service_name (str): Имя сервиса, которое станет префиксом основной очереди.
        retry_stage_ttl_ms (Mapping[str, int] | None, optional): Опциональный маппинг суффиксов ступеней на их TTL в
        мс (полезно для тестов, чтобы не ждать реальные тайминги). По дефолту берет `RETRY_STAGE_TTL_MS`.

    Returns:
        AbstractQueue: Ссылка на инстанс созданной или найденной основной quorum-очереди.

    Side Effects:
        Создает эксчейнджи и очереди в брокере, если их там не было, вешает биндинги."""
    events_exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME, ensure=True)
    dlx = await channel.declare_exchange(
        DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True
    )
    main_queue_name = f"{service_name}.user-events"
    main_queue = await channel.declare_queue(
        main_queue_name,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": main_queue_name,
        },
    )
    await main_queue.bind(events_exchange, routing_key="user.*.v1")
    stage_ttl_ms = (
        RETRY_STAGE_TTL_MS if retry_stage_ttl_ms is None else retry_stage_ttl_ms
    )
    for suffix, ttl_ms in stage_ttl_ms.items():
        await channel.declare_queue(
            f"{main_queue_name}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": main_queue_name,
                "x-message-ttl": ttl_ms,
            },
        )
    dlq = await channel.declare_queue(f"{main_queue_name}.dlq", durable=True)
    await dlq.bind(dlx, routing_key=main_queue_name)
    return main_queue

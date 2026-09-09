# ruff: noqa: E501
from collections.abc import Iterable, Mapping

from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractQueue

from kernel_platform.outbox.settings import EVENTS_EXCHANGE_NAME

DLX_EXCHANGE_NAME = "productsflow.dlx"
COMMANDS_EXCHANGE_NAME = "productsflow.commands"
RETRY_STAGE_TTL_MS = {"retry.5s": 5000, "retry.30s": 30000, "retry.2m": 120000}


async def declare_topology(
    channel: AbstractChannel,
    service_name: str,
    *,
    retry_stage_ttl_ms: Mapping[str, int] | None = None,
    queue_name: str | None = None,
    routing_keys: Iterable[str] = ("user.*.v1",),
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
    # Every worker owns the declaration it needs.  This makes a consumer safe
    # to start before the producer which would otherwise create the exchange.
    events_exchange = await channel.declare_exchange(
        EVENTS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    dlx = await channel.declare_exchange(
        DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True
    )
    main_queue_name = queue_name or f"{service_name}.user-events"
    main_queue = await channel.declare_queue(
        main_queue_name,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": main_queue_name,
        },
    )
    for routing_key in routing_keys:
        await main_queue.bind(events_exchange, routing_key=routing_key)
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


async def declare_command_topology(
    channel: AbstractChannel,
    command_type: str,
    *,
    retry_stage_ttl_ms: Mapping[str, int] | None = None,
) -> AbstractQueue:
    """Declares the one durable queue owned by a command type.

    Commands are point-to-point messages: their versioned routing key maps to
    one stable queue name rather than a service-defined queue.  Repeated
    declarations therefore reuse the exact same queue and cannot turn one
    command into a broker fan-out.
    """
    commands_exchange = await channel.declare_exchange(
        COMMANDS_EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )
    dlx = await channel.declare_exchange(
        DLX_EXCHANGE_NAME, ExchangeType.DIRECT, durable=True
    )
    owner_queue_name = f"commands.{command_type}"
    owner_queue = await channel.declare_queue(
        owner_queue_name,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            "x-dead-letter-routing-key": owner_queue_name,
        },
    )
    await owner_queue.bind(commands_exchange, routing_key=command_type)
    stage_ttl_ms = (
        RETRY_STAGE_TTL_MS if retry_stage_ttl_ms is None else retry_stage_ttl_ms
    )
    for suffix, ttl_ms in stage_ttl_ms.items():
        await channel.declare_queue(
            f"{owner_queue_name}.{suffix}",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": owner_queue_name,
                "x-message-ttl": ttl_ms,
            },
        )
    dlq = await channel.declare_queue(f"{owner_queue_name}.dlq", durable=True)
    await dlq.bind(dlx, routing_key=owner_queue_name)
    return owner_queue

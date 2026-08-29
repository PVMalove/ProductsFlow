from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractQueue

from kernel_platform.outbox.publisher import EVENTS_EXCHANGE_NAME

DLX_EXCHANGE_NAME = "productsflow.dlx"

# Тюнинг-параметр (ADR 0015): три ступени TTL, не полноценный exponential
# backoff — суффикс становится частью имени очереди-ступени.
_RETRY_STAGE_TTL_MS = {
    "retry.5s": 5_000,
    "retry.30s": 30_000,
    "retry.2m": 120_000,
}


async def declare_topology(
    channel: AbstractChannel, service_name: str
) -> AbstractQueue:
    """Идемпотентно объявляет топологию потребителя `user.*.v1` (ADR 0015):
    DLX, основную quorum-очередь `<service>.user-events` (биндинг на уже
    существующий `productsflow.events`, объявленный identity-service — здесь
    он только passive-проверяется через `get_exchange`, не переобъявляется),
    три TTL-очереди-ступени без потребителей и DLQ. `aio-pika` declare
    идемпотентен при совпадающих параметрах — повторный вызов при рестарте
    процесса не бросает `PRECONDITION_FAILED` и не создаёт дублей.

    Управление retry-лестницей (чтение `x-death`, публикация в конкретную
    ступень, `ack`/`reject`) — код консьюмера, не этой функции (issue #66/#67).
    """
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

    for suffix, ttl_ms in _RETRY_STAGE_TTL_MS.items():
        await channel.declare_queue(
            f"{main_queue_name}.{suffix}",
            durable=True,
            arguments={
                # Default exchange ("") — доставка в одну конкретную очередь,
                # не топик-fanout (ADR 0015 явно отклоняет возврат через
                # productsflow.events).
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": main_queue_name,
                "x-message-ttl": ttl_ms,
            },
        )

    dlq = await channel.declare_queue(f"{main_queue_name}.dlq", durable=True)
    await dlq.bind(dlx, routing_key=main_queue_name)

    return main_queue

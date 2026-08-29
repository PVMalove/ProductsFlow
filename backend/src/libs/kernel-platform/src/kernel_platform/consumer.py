import logging
from collections.abc import Awaitable, Callable, Sequence

import aio_pika
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractQueue,
    ConsumerTag,
    HeadersType,
)

from kernel_platform.topology import RETRY_STAGE_TTL_MS

logger = logging.getLogger(__name__)

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]

_RETRY_STAGE_NAMES = tuple(RETRY_STAGE_TTL_MS)


def _next_stage_index(headers: HeadersType, stage_queue_names: Sequence[str]) -> int:
    """Определяет номер следующей ступени лестницы по `x-death` (ADR 0015).

    Каждый переход между ступенями — manual-republish через default exchange,
    не `reject`, поэтому `x-death`, который брокер добавляет при очередном
    TTL-дед-леттеринге, не накапливается по всем пройденным ступеням сразу:
    проверено эмпирически на RabbitMQ 4.1 — при следующем дед-леттеринге
    брокер заменяет массив одной записью, отражающей только ступень, из
    которой сообщение только что вернулось, а не сохраняет более ранние.
    Поэтому здесь ищется САМАЯ ПРОДВИНУТАЯ по порядку ступень среди того, что
    реально есть в заголовке (не сумма/количество записей) — это устойчиво
    и к замене на одну запись, и к гипотетическому накоплению нескольких.
    """
    x_death = headers.get("x-death")
    if not isinstance(x_death, list):
        return 0

    last_stage_index = -1
    for entry in x_death:
        if not isinstance(entry, dict):
            continue
        queue_name = entry.get("queue")
        if queue_name not in stage_queue_names:
            continue
        stage_index = stage_queue_names.index(queue_name)
        if stage_index > last_stage_index:
            last_stage_index = stage_index
    return last_stage_index + 1


async def consume(queue: AbstractQueue, handler: MessageHandler) -> ConsumerTag:
    """Обёртка-консьюмер над `queue.consume` с полной retry-лестницей (ADR
    0015, issue #110). Обработчик отработал без исключения → `message.ack()`.

    Исключение в обработчике → по номеру следующей ступени, вычисленному из
    `x-death` (`_next_stage_index`): меньше трёх ступеней пройдено —
    сообщение публикуется напрямую в очередь нужной ступени через default
    exchange (routing key = имя ступени-очереди), а исходная доставка
    `ack`'ается, не `reject`'ается — `reject` увёл бы сообщение через
    статический DLX основной очереди мимо лестницы. Три ступени исчерпаны —
    `reject(requeue=False)`, что уводит сообщение в DLQ тем же путём, что и
    раньше (issue #109).

    Ступень-очередь по истечении своего TTL уже дед-леттеруется обратно в
    основную очередь того же сервиса — это статически объявлено в
    `declare_topology` (ADR 0015), здесь только чтение `x-death` и выбор
    следующей ступени.
    """
    stage_queue_names = tuple(f"{queue.name}.{suffix}" for suffix in _RETRY_STAGE_NAMES)

    async def _on_message(message: AbstractIncomingMessage) -> None:
        try:
            await handler(message)
        except Exception:
            next_stage_index = _next_stage_index(message.headers, stage_queue_names)
            if next_stage_index >= len(stage_queue_names):
                logger.exception(
                    "Consumer %s: ступени лестницы исчерпаны (попытка %d),"
                    " сообщение %s уходит в DLQ",
                    queue.name,
                    next_stage_index + 1,
                    message.message_id,
                )
                await message.reject(requeue=False)
                return

            stage_queue_name = stage_queue_names[next_stage_index]
            logger.warning(
                "Consumer %s: обработчик бросил исключение (попытка %d),"
                " сообщение %s уходит в ступень %s",
                queue.name,
                next_stage_index + 1,
                message.message_id,
                stage_queue_name,
                exc_info=True,
            )
            await queue.channel.default_exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    headers=message.headers,
                    content_type=message.content_type,
                    message_id=message.message_id,
                    # Без явного delivery_mode `aio-pika` подставил бы
                    # NOT_PERSISTENT (см. build_message в outbox/publisher.py)
                    # — сообщение потерялось бы при рестарте брокера, пока
                    # сидит в очереди ступени. Форвардим режим исходного
                    # сообщения, а не жёстко PERSISTENT.
                    delivery_mode=message.delivery_mode,
                ),
                routing_key=stage_queue_name,
            )
            await message.ack()
        else:
            await message.ack()

    return await queue.consume(_on_message, no_ack=False)

# ruff: noqa: E501
import logging
from collections.abc import Awaitable, Callable, Sequence

import aio_pika
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractQueue,
    ConsumerTag,
    HeadersType,
)
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind

from kernel_platform.outbox.trace_context import w3c_carrier
from kernel_platform.topology import RETRY_STAGE_TTL_MS

logger = logging.getLogger(__name__)
MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]
_RETRY_STAGE_NAMES = tuple(RETRY_STAGE_TTL_MS)


def _extract_message_context(headers: HeadersType) -> Context:
    """Extracts the W3C parent context carried in AMQP headers.

    Missing or malformed `traceparent`/`tracestate` values leave the
    returned context empty, so `start_as_current_span` below starts a new
    root span instead of raising.
    """
    return propagate.extract(w3c_carrier(dict(headers)))


def next_stage_index(headers: HeadersType, stage_queue_names: Sequence[str]) -> int:
    """Определяет номер следующей ступени лестницы по заголовку `x-death`.

    Каждый переход между ступенями — manual-republish через default exchange, не `reject`, поэтому `x-death`,
    который брокер добавляет при очередном TTL-дед-леттеринге, не накапливается по всем пройденным ступеням сразу.
    Брокер заменяет массив одной записью, отражающей только ступень, из которой сообщение только что вернулось.
    Ищется самая продвинутая ступень в заголовке.

    Args:
        headers (HeadersType): AMQP заголовки сообщения, откуда дергаем `x-death`.
        stage_queue_names (Sequence[str]): Кортеж имен очередей-ступеней по порядку эскалации.

    Returns:
        int: Индекс следующей ступени в массиве stage_queue_names, куда надо отправить сообщение.
             Если мы на последней ступени, вернет значение >= len(stage_queue_names)."""
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


async def consume(
    queue: AbstractQueue,
    handler: MessageHandler,
    *,
    prefetch_count: int | None = None,
) -> ConsumerTag:
    """Обёртка-консьюмер над `queue.consume` с полной retry-лестницей.

    Под капотом подписывается на очередь и хэндлит эксепшены обработчика.
    Если обработчик отработал чисто — кидаем `ack`.
    Если упал — вычисляем следующую ступень через `_next_stage_index` по `x-death`.
    Если ступеней еще хватает, мануально паблишим сообщение напрямую в очередь нужной ступени через default exchange,
    а исходное сообщение аккаем (чтобы оно не улетело в статический DLX).
    Если ступени закончились — режектим с `requeue=False`, что отправляет месседж в DLQ.

    Args:
        queue (AbstractQueue): Очередь `aio_pika`, из которой будем консьюмить.
        handler (MessageHandler): Асинхронный коллбэк для обработки каждого сообщения.
        prefetch_count (int | None): Если задан, ограничивает канал этим QoS
            перед подпиской — обработчик получает следующее сообщение только
            после `ack`/`reject` предыдущего. По умолчанию `None` (без
            ограничения, брокер доставляет и `_on_message` обрабатывает
            сообщения параллельно) — сохраняет прежнее поведение для
            консьюмеров без зависимости от порядка. Consumers, чья read-модель
            версионируется частичным upsert (не полным снапшотом), обязаны
            передавать `prefetch_count=1`: без строгого порядка обработки более
            новое по `last_applied_outbox_id` событие может закоммититься раньше
            более старого, и тогда version guard навсегда отбросит поле,
            которое нёс только отставший apply.

    Returns:
        ConsumerTag: Тег созданного консьюмера, по которому его можно будет остановить.

    Side Effects:
        Мутирует стейт брокера (аккает, режектит или паблишит месседжи)."""
    if prefetch_count is not None:
        await queue.channel.set_qos(prefetch_count=prefetch_count)
    stage_queue_names = tuple(
        (f"{queue.name}.{suffix}" for suffix in _RETRY_STAGE_NAMES)
    )
    tracer = trace.get_tracer(__name__)

    async def _on_message(message: AbstractIncomingMessage) -> None:
        """Внутренний коллбэк для маппинга входящего сообщения на хэндлер и логику ретраев.

        Хэндлер выполняется под спаном `consume_message`, продолжающим трейс
        паблишера через W3C-заголовки сообщения (ADR 0015); retry/ack/reject
        логика ниже не меняется.

        Args:
            message (AbstractIncomingMessage): Сырое сообщение из RabbitMQ."""
        try:
            with tracer.start_as_current_span(
                "consume_message",
                context=_extract_message_context(message.headers),
                kind=SpanKind.CONSUMER,
            ):
                await handler(message)
        except Exception:
            retry_stage_index = next_stage_index(message.headers, stage_queue_names)
            if retry_stage_index >= len(stage_queue_names):
                logger.exception(
                    "Consumer %s: ступени лестницы исчерпаны (попытка %d), сообщение %s уходит в DLQ",
                    queue.name,
                    retry_stage_index + 1,
                    message.message_id,
                )
                await message.reject(requeue=False)
                return
            stage_queue_name = stage_queue_names[retry_stage_index]
            logger.warning(
                "Consumer %s: обработчик бросил исключение (попытка %d), сообщение %s уходит в ступень %s",
                queue.name,
                retry_stage_index + 1,
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
                    type=message.type,
                    delivery_mode=message.delivery_mode,
                ),
                routing_key=stage_queue_name,
            )
            await message.ack()
        else:
            await message.ack()

    return await queue.consume(_on_message, no_ack=False)

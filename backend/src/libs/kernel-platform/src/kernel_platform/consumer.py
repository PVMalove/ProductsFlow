import logging
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue, ConsumerTag

logger = logging.getLogger(__name__)

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


async def consume(queue: AbstractQueue, handler: MessageHandler) -> ConsumerTag:
    """Обёртка-консьюмер над `queue.consume` (issue #109): happy path без
    лестницы ступеней. Обработчик отработал без исключения → `message.ack()`.
    Исключение в обработчике → `message.reject(requeue=False)`, что уводит
    сообщение в DLQ через уже объявленный статический `x-dead-letter-exchange`
    основной очереди (ADR 0015) — без разбора `x-death` и публикации в
    конкретную ступень лестницы, это следующий тикет (issue #110).
    """

    async def _on_message(message: AbstractIncomingMessage) -> None:
        try:
            await handler(message)
        except Exception:
            logger.exception(
                "Consumer %s: обработчик бросил исключение, сообщение %s уходит в DLQ",
                queue.name,
                message.message_id,
            )
            await message.reject(requeue=False)
        else:
            await message.ack()

    return await queue.consume(_on_message, no_ack=False)

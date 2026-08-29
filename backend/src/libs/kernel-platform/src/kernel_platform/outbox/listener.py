import asyncio
import logging
from types import TracebackType

import asyncpg

logger = logging.getLogger(__name__)

# Должно совпадать буквально с NOTIFICATION_CHANNEL в Alembic-ревизии
# identity-service (05fc06c154bc_outbox_messages_notify_trigger.py), которая
# создаёт `NOTIFY` на стороне INSERT — оба конца координируются только через
# это имя, без общего импорта между Alembic и приложением.
NOTIFICATION_CHANNEL = "outbox_messages_inserted"


def to_asyncpg_dsn(sqlalchemy_url: str) -> str:
    """SQLAlchemy кодирует драйвер в схему URL (`postgresql+asyncpg://...`);
    `asyncpg.connect()` ожидает голую схему `postgresql://`.
    """
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class OutboxListener:
    """Выделенное `LISTEN`-соединение на канал вставки в `outbox_messages`
    (ADR 0014, issue #102): гибридное пробуждение — `NOTIFY` ускоряет реакцию
    `OutboxPublisher` до «почти мгновенно» в счастливом пути, но не заменяет
    poll — `wait_for_wakeup` всегда ограничена таймаутом, поэтому потерянный
    `NOTIFY` (не подписаны в момент отправки — рестарт, разрыв соединения)
    не блокирует доставку: следующий poll-тик всё равно подхватит строку.

    `asyncio.Event` даёт «липкое» пробуждение без гонки: `NOTIFY`, пришедший
    во время предыдущего `run_once()` (до того, как воркер снова начал
    ждать), не теряется — `set()` до `wait()` всё равно немедленно
    разбудит следующий `wait_for_wakeup`.
    """

    def __init__(self, dsn: str, *, channel: str = NOTIFICATION_CHANNEL) -> None:
        self._dsn = dsn
        self._channel = channel
        self._connection: asyncpg.Connection | None = None
        self._wakeup = asyncio.Event()

    async def start(self) -> None:
        self._connection = await asyncpg.connect(self._dsn)
        await self._connection.add_listener(self._channel, self._handle_notify)

    async def stop(self) -> None:
        if self._connection is None:
            return
        await self._connection.remove_listener(self._channel, self._handle_notify)
        await self._connection.close()
        self._connection = None

    async def wait_for_wakeup(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=timeout)
        except TimeoutError:
            pass
        finally:
            self._wakeup.clear()

    def _handle_notify(
        self,
        _connection: asyncpg.Connection,
        _pid: int,
        _channel: str,
        _payload: object,
    ) -> None:
        self._wakeup.set()

    async def __aenter__(self) -> "OutboxListener":
        await self.start()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.stop()

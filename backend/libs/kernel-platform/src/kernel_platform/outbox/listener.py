import asyncio
import logging
from types import TracebackType

import asyncpg

logger = logging.getLogger(__name__)
NOTIFICATION_CHANNEL = "outbox_messages_inserted"


def to_asyncpg_dsn(sqlalchemy_url: str) -> str:
    """Адаптирует DSN-строку из формата SQLAlchemy в формат, понятный чистому asyncpg.

    Args:
        sqlalchemy_url (str): Урл вида `postgresql+asyncpg://...`.

    Returns:
        str: Урл вида `postgresql://...`."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class OutboxListener:
    """Выделенное `LISTEN`-соединение на канал вставки в `outbox_messages`:
     гибридное пробуждение — `NOTIFY` ускоряет реакцию
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
        """Инициализирует листенер для LISTEN/NOTIFY.

        Args:
            dsn (str): Строка подключения к БД.
            channel (str): Имя pg-канала, который слушаем.
                По умолчанию `NOTIFICATION_CHANNEL`.
        """
        self._dsn = dsn
        self._channel = channel
        self._connection: asyncpg.Connection | None = None
        self._wakeup = asyncio.Event()

    async def start(self) -> None:
        """Поднимает коннект к постгре и вешает подписку на pg-канал.

        Мутирует внутренний стейт, сохраняя инстанс `asyncpg.Connection`."""
        self._connection = await asyncpg.connect(self._dsn)
        await self._connection.add_listener(self._channel, self._handle_notify)

    async def stop(self) -> None:
        """Гасит коннект и снимает подписку с pg-канала.

        Высвобождает ресурсы, если коннект был поднят."""
        if self._connection is None:
            return
        await self._connection.remove_listener(self._channel, self._handle_notify)
        await self._connection.close()
        self._connection = None

    async def wait_for_wakeup(self, timeout: float) -> None:
        """Блокирующее (асинхронно) ожидание эвента о новом сообщении или таймаута.

        Ждет триггера от `asyncio.Event`. Если событие не стрельнуло за timeout —
        проглатывает `TimeoutError` и выходит.
        В любом случае сбрасывает флаг эвента перед выходом.

        Args:
            timeout (float): Максимальное время ожидания (в секундах)."""
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
        """Стреляет эвент при получении `NOTIFY` из постгре.

        Взводит `asyncio.Event`, разблокируя ожидающих в `wait_for_wakeup`.

        Args:
            _connection, _pid, _channel, _payload: Сырые параметры коллбэка
                `asyncpg`.
        """
        self._wakeup.set()

    async def __aenter__(self) -> "OutboxListener":
        """Точка входа асинхронного контекстного менеджера, стартует листенер."""
        await self.start()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Точка выхода асинхронного контекстного менеджера, стопает листенер."""
        await self.stop()

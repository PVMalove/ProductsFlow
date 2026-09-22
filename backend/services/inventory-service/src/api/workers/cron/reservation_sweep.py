# ruff: noqa: E501
"""TTL-sweep для просроченных резервов (issue #370, D6) — periodic
polling-loop, мирует форму `outbox_worker.py`'s цикла (try/except +
`asyncio.sleep` на ошибке). Одна транзакция на просроченный `Reservation`
(не батч на весь sweep-проход) — `ReservationRepository.claim_expired()`
делает `SELECT ... FOR UPDATE SKIP LOCKED`, переиспользует тот же
`ReleaseInventoryReservationCommandHandler`, что и явный manual-release
(D1/D8: единый структурный эффект, различённый только `reason`)."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.commands.release_inventory_reservation import (
    ReleaseInventoryReservationCommand,
    ReleaseInventoryReservationCommandHandler,
)
from infrastructure.db.inventory_repository import InventoryRepository
from infrastructure.db.reservation_repository import ReservationRepository

logger = logging.getLogger(__name__)


async def run_once(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime
) -> int:
    """Один sweep-проход: одна транзакция на каждый просроченный `ACTIVE`-
    резерв, повторяется, пока `claim_expired` находит хотя бы один. Возвращает
    число освобождённых резервов — тестируемо через фиксированный `now`."""
    released = 0
    while True:
        async with session_factory() as session:
            async with session.begin():
                reservation_repo = ReservationRepository(session)
                expired = await reservation_repo.claim_expired(now=now, limit=1)
                if not expired:
                    return released

                handler = ReleaseInventoryReservationCommandHandler(
                    InventoryRepository(session), reservation_repo
                )
                await handler.execute(
                    ReleaseInventoryReservationCommand(
                        order_id=expired[0].id, reason="expired"
                    )
                )
        released += 1


async def run(
    session_factory: async_sessionmaker[AsyncSession], *, interval_seconds: float
) -> None:
    while True:
        try:
            released = await run_once(session_factory, now=datetime.now(UTC))
            if released:
                logger.info(
                    "inventory-worker: TTL sweep released %d expired reservation(s)",
                    released,
                )
        except Exception:
            logger.exception("inventory-worker: reservation TTL sweep pass failed")
        await asyncio.sleep(interval_seconds)

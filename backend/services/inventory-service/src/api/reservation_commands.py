# ruff: noqa: E501
"""Message-driven адаптеры `inventory.reserve.v1`/`inventory.release.v1` —
`CommandHandler`-форма (`kernel_platform.commands.CommandHandler`), мирруют
`api/worker.py::handle_product_event` (issue #367, находка 3): чистая функция
`(session, command) -> None`, инстанцирует репозитории напрямую поверх
переданной сессии — никакого UoW/`.commit()`, транзакцией управляет
`consume_command` (issue #370, D8)."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from kernel_platform.commands import Command, CommandHandler
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.release_inventory_reservation import (
    ReleaseInventoryReservationCommand,
    ReleaseInventoryReservationCommandHandler,
)
from application.commands.reserve_inventory_lines import (
    ReservationLineRequest,
    ReserveInventoryLinesCommand,
    ReserveInventoryLinesCommandHandler,
)
from core.settings import settings
from infrastructure.db.inventory_repository import InventoryRepository
from infrastructure.db.reservation_repository import ReservationRepository

logger = logging.getLogger(__name__)


def _parse_reserve_payload(payload: dict[str, Any]) -> ReserveInventoryLinesCommand:
    order_id = uuid.UUID(str(payload["order_id"]))
    lines = tuple(
        ReservationLineRequest(
            product_id=uuid.UUID(str(line["product_id"])),
            quantity=int(line["quantity"]),
        )
        for line in payload["lines"]
    )
    return ReserveInventoryLinesCommand(order_id=order_id, lines=lines)


def _parse_release_payload(
    payload: dict[str, Any],
) -> ReleaseInventoryReservationCommand:
    order_id = uuid.UUID(str(payload["order_id"]))
    return ReleaseInventoryReservationCommand(order_id=order_id, reason="manual")


async def handle_reserve_command(session: AsyncSession, command: Command) -> None:
    reserve_command = _parse_reserve_payload(command.payload)
    handler = ReserveInventoryLinesCommandHandler(
        InventoryRepository(session),
        ReservationRepository(session),
        ttl_minutes=settings.inventory_reservation_ttl_minutes,
    )
    await handler.execute(reserve_command, now=datetime.now(UTC))
    logger.info(
        "inventory-worker: processed inventory.reserve.v1 for order_id=%s",
        reserve_command.order_id,
    )


async def handle_release_command(session: AsyncSession, command: Command) -> None:
    release_command = _parse_release_payload(command.payload)
    handler = ReleaseInventoryReservationCommandHandler(
        InventoryRepository(session), ReservationRepository(session)
    )
    await handler.execute(release_command)
    logger.info(
        "inventory-worker: processed inventory.release.v1 for order_id=%s",
        release_command.order_id,
    )


# Единый реестр command_type -> handler (issue #370, Seams for TDD #6) —
# `api/worker.py::main()` регистрирует консьюмеры по нему, тест
# `test_reservation_worker_seams.py` ловит забытую регистрацию.
COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "inventory.reserve.v1": handle_reserve_command,
    "inventory.release.v1": handle_release_command,
}

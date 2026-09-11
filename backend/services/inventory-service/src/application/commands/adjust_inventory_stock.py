# ruff: noqa: E501
"""Команда и handler admin-корректировки остатка (issue #367)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from contracts.inventory import InventoryView
from domain.errors import InventoryErrors
from domain.unit_of_work import InventoryUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdjustInventoryStockCommand:
    """DTO для аудитируемой admin-корректировки остатка."""

    actor: Actor
    product_id: uuid.UUID
    delta: int
    reason: str


class AdjustInventoryStockCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Аудитируемая корректировка остатка товара администратором.
    Validations: Остаток после применения `delta` не может стать отрицательным (Inventory.adjust).
    Side Effects: Обновляется quantity в репозитории, пишется InventoryAuditLog (ORM listener), возможна строка Outbox (InventoryAdjusted).
    """

    def __init__(self, uow: InventoryUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, command: AdjustInventoryStockCommand
    ) -> Result[InventoryView]:
        # Авторизация уже прошла на уровне FastAPI-зависимости (AdminActor,
        # архитектурный бриф #367 — единственная операция сервиса, требующая
        # роль) — handler ничего не проверяет по `command.actor`, кроме
        # логирования.
        async with self._uow:
            result = await self._uow.inventory.adjust(
                command.product_id, command.delta, reason=command.reason
            )
            if result is None:
                logger.warning(
                    "Корректировка остатка отклонена: product_id=%s не найден",
                    command.product_id,
                )
                return Result[InventoryView].fail(InventoryErrors.inventory_not_found())
            if result.is_err:
                logger.warning(
                    "Корректировка остатка отклонена: product_id=%s code=%s",
                    command.product_id,
                    result.error.code,
                )
                return Result[InventoryView].fail(result.error)
            await self._uow.commit()
        logger.info(
            "Остаток скорректирован: product_id=%s delta=%s actor=%s",
            command.product_id,
            command.delta,
            command.actor.id,
        )
        return Result[InventoryView].ok(InventoryView.from_domain(result.value))

from typing import Annotated

from fastapi import Depends

from application.commands import AdjustInventoryStockCommandHandler
from domain.unit_of_work import InventoryUnitOfWork
from infrastructure.db.session import DbSessionDI
from infrastructure.db.unit_of_work import SqlInventoryUnitOfWork


def get_inventory_uow(session: DbSessionDI) -> InventoryUnitOfWork:
    return SqlInventoryUnitOfWork(session)


InventoryUnitOfWorkDI = Annotated[InventoryUnitOfWork, Depends(get_inventory_uow)]


def get_adjust_inventory_stock_handler(
    uow: InventoryUnitOfWorkDI,
) -> AdjustInventoryStockCommandHandler:
    return AdjustInventoryStockCommandHandler(uow)


AdjustInventoryStockDI = Annotated[
    AdjustInventoryStockCommandHandler, Depends(get_adjust_inventory_stock_handler)
]


__all__ = [
    "AdjustInventoryStockDI",
    "InventoryUnitOfWorkDI",
    "get_adjust_inventory_stock_handler",
    "get_inventory_uow",
]

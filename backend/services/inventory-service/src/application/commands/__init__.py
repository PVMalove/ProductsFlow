"""Публичный command-side интерфейс для application use case'ов inventory."""

from application.commands.adjust_inventory_stock import (
    AdjustInventoryStockCommand,
    AdjustInventoryStockCommandHandler,
)

__all__ = [
    "AdjustInventoryStockCommand",
    "AdjustInventoryStockCommandHandler",
]

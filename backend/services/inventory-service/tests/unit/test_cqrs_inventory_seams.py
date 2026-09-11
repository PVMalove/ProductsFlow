"""Перечисление command handler'ов inventory (issue #367, по образцу
catalog's test_cqrs_catalog_seams.py) — ловит забытую регистрацию нового
handler'а. Inventory не несёт query-side use case'ов в #367 (нет публичного
read-эндпоинта, см. архитектурный бриф — «Selected option — API»)."""

from application.commands import (
    AdjustInventoryStockCommand,
    AdjustInventoryStockCommandHandler,
)


def test_inventory_application_exposes_exactly_one_command_handler() -> None:
    command_types = (AdjustInventoryStockCommandHandler,)
    command_dto_types = (AdjustInventoryStockCommand,)

    assert all(hasattr(handler_type, "execute") for handler_type in command_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in command_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in command_dto_types
    )

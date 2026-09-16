"""Перечисление command/query handler'ов order-service (issue #369, Seams for
TDD #4, по образцу payment's test_cqrs_payment_seams.py) — ловит забытую
регистрацию нового handler'а."""

from application.commands import (
    AddCartLineCommand,
    AddCartLineCommandHandler,
    CheckoutCommand,
    CheckoutCommandHandler,
    RemoveCartLineCommand,
    RemoveCartLineCommandHandler,
    UpdateCartLineQuantityCommand,
    UpdateCartLineQuantityCommandHandler,
)
from application.queries import GetCartQuery, GetCartQueryHandler


def test_order_application_exposes_exactly_four_command_handlers() -> None:
    command_types = (
        AddCartLineCommandHandler,
        UpdateCartLineQuantityCommandHandler,
        RemoveCartLineCommandHandler,
        CheckoutCommandHandler,
    )
    command_dto_types = (
        AddCartLineCommand,
        UpdateCartLineQuantityCommand,
        RemoveCartLineCommand,
        CheckoutCommand,
    )

    assert all(hasattr(handler_type, "execute") for handler_type in command_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in command_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in command_dto_types
    )


def test_order_application_exposes_exactly_one_query_handler() -> None:
    query_types = (GetCartQueryHandler,)
    query_dto_types = (GetCartQuery,)

    assert all(hasattr(handler_type, "execute") for handler_type in query_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in query_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in query_dto_types
    )

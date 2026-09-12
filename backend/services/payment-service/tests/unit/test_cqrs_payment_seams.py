"""Перечисление command/query handler'ов payment (issue #368, по образцу
inventory's test_cqrs_inventory_seams.py) — ловит забытую регистрацию нового
handler'а."""

from application.commands import (
    AuthorizePaymentCommand,
    AuthorizePaymentCommandHandler,
    CapturePaymentCommand,
    CapturePaymentCommandHandler,
    VoidPaymentCommand,
    VoidPaymentCommandHandler,
)
from application.queries import LookupPaymentQuery, LookupPaymentQueryHandler


def test_payment_application_exposes_exactly_three_command_handlers() -> None:
    command_types = (
        AuthorizePaymentCommandHandler,
        VoidPaymentCommandHandler,
        CapturePaymentCommandHandler,
    )
    command_dto_types = (
        AuthorizePaymentCommand,
        VoidPaymentCommand,
        CapturePaymentCommand,
    )

    assert all(hasattr(handler_type, "execute") for handler_type in command_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in command_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in command_dto_types
    )


def test_payment_application_exposes_exactly_one_query_handler() -> None:
    query_types = (LookupPaymentQueryHandler,)
    query_dto_types = (LookupPaymentQuery,)

    assert all(hasattr(handler_type, "execute") for handler_type in query_types)
    assert all(not hasattr(handler_type, "handle") for handler_type in query_types)
    assert all(
        hasattr(dto_type, "__dataclass_fields__") for dto_type in query_dto_types
    )

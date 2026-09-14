# ruff: noqa: E501
"""Message-driven адаптеры `payment.authorize.v1`/`payment.void.v1` (issue #371)
— `CommandHandler`-форма (`kernel_platform.commands.CommandHandler`): claims
the inbox row (уже даёт `consume_command` бесплатно), вызывает неизменные
`AuthorizePaymentCommandHandler`/`VoidPaymentCommandHandler` (issue #368)
внутри `PaymentCommandUnitOfWork` (архитектурный бриф D5), и вставляет
коррелированный факт результата напрямую в `outbox_messages` (D3) — без
доменных событий, `PaymentAuthorization` остаётся нетронутым, так что
существующий HTTP-путь продолжает вести себя ровно как раньше."""

import logging
import uuid
from datetime import UTC, datetime

from kernel_platform.commands import Command, CommandHandler
from kernel_platform.outbox.models import OutboxMessage
from kernel_platform.outbox.trace_context import serialize_trace_context
from kernel_platform.security import Actor, ActorRole
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.authorize_payment import (
    AuthorizePaymentCommand,
    AuthorizePaymentCommandHandler,
)
from application.commands.void_payment import (
    VoidPaymentCommand,
    VoidPaymentCommandHandler,
)
from core.psp import build_psp_client
from core.settings import settings
from domain.entities.payment_authorization import PaymentAuthorizationStatus
from infrastructure.db.unit_of_work import PaymentCommandUnitOfWork

logger = logging.getLogger(__name__)

# Синтетический actor для message-driven вызовов (архитектурный бриф D4):
# `AuthorizePaymentCommand`/`VoidPaymentCommand` требуют `actor: Actor`,
# используемый только для логирования (issue #368) — ни один из двух
# хендлеров не проверяет роль. Nil-UUID узнаваем в логах как «не человек».
_SYSTEM_ACTOR = Actor(id=uuid.UUID(int=0), role=ActorRole.USER)

# Decline/timeout — `Result.ok`, не `Result.fail` (D2/находка 9):
# `PaymentAuthorization.create()` персистит строку в обоих случаях, различие
# идёт по `view.status`, не по `result.is_err`.
_AUTHORIZE_EVENT_TYPE_BY_STATUS: dict[PaymentAuthorizationStatus, str] = {
    PaymentAuthorizationStatus.AUTHORIZED: "payment.authorized.v1",
    PaymentAuthorizationStatus.DECLINED: "payment.authorization_declined.v1",
    PaymentAuthorizationStatus.AUTHORIZATION_UNKNOWN: "payment.authorization_timed_out.v1",
}


def _result_outbox_message(
    *, event_type: str, authorization_id: uuid.UUID, command: Command
) -> OutboxMessage:
    return OutboxMessage(
        aggregate_type="PaymentAuthorization",
        aggregate_id=authorization_id,
        event_type=event_type,
        payload={
            "authorization_id": str(authorization_id),
            "correlation_id": command.correlation_id,
            "causation_id": str(command.causation_id),
        },
        occurred_at=datetime.now(UTC),
        trace_context=serialize_trace_context(),
    )


async def handle_authorize_command(session: AsyncSession, command: Command) -> None:
    payload = command.payload
    uow = PaymentCommandUnitOfWork(session)
    handler = AuthorizePaymentCommandHandler(uow, build_psp_client(settings))
    result = await handler.execute(
        AuthorizePaymentCommand(
            actor=_SYSTEM_ACTOR,
            idempotency_key=str(command.command_id),
            amount=int(payload["amount"]),
            payment_method_token=str(payload["payment_method_token"]),
        )
    )
    if result.is_err:
        # invalid_amount / unknown_test_scenario_token / idempotency_conflict
        # — все три, при idempotency_key = str(command_id) (D6), означают
        # испорченную команду от продюсера, не легитимный повтор (D7) — пусть
        # consume()'s retry/DLQ-лестница обработает как транзиентную/
        # permanent ошибку.
        raise ValueError(f"payment.authorize.v1 rejected: {result.error.code}")

    view = result.value
    event_type = _AUTHORIZE_EVENT_TYPE_BY_STATUS[
        PaymentAuthorizationStatus(view.status)
    ]
    session.add(
        _result_outbox_message(
            event_type=event_type, authorization_id=view.id, command=command
        )
    )


async def handle_void_command(session: AsyncSession, command: Command) -> None:
    authorization_id = uuid.UUID(str(command.payload["authorization_id"]))
    uow = PaymentCommandUnitOfWork(session)
    handler = VoidPaymentCommandHandler(uow)
    result = await handler.execute(
        VoidPaymentCommand(
            actor=_SYSTEM_ACTOR,
            authorization_id=authorization_id,
            idempotency_key=str(command.command_id),
        )
    )
    if result.is_err:
        # authorization_not_found / invalid_authorization_state — легитимная
        # гонка/повтор в распределённой системе (D7), не баг продюсера —
        # тихий no-op, зеркалирует ReleaseInventoryReservationCommandHandler
        # (issue #370).
        logger.warning(
            "payment.void.v1: no-op for authorization_id=%s code=%s",
            authorization_id,
            result.error.code,
        )
        return

    session.add(
        _result_outbox_message(
            event_type="payment.voided.v1",
            authorization_id=authorization_id,
            command=command,
        )
    )


# Единый реестр command_type -> handler (issue #371, Seams for TDD #2) —
# `api/worker.py::main()` регистрирует консьюмеры по нему, тест
# `test_payment_worker_seams.py` ловит забытую регистрацию.
COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "payment.authorize.v1": handle_authorize_command,
    "payment.void.v1": handle_void_command,
}

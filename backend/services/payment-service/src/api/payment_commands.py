# ruff: noqa: E501
"""Message-driven адаптеры `payment.authorize.v1`/`payment.void.v1` (issue #371)
— `CommandHandler`-форма (`kernel_platform.commands.CommandHandler`): claims
the inbox row (уже даёт `consume_command` бесплатно), вызывает неизменные
`AuthorizePaymentCommandHandler`/`VoidPaymentCommandHandler` (issue #368)
внутри `PaymentCommandUnitOfWork` (архитектурный бриф D5), и вставляет
коррелированный факт результата напрямую в `outbox_messages` (D3) — без
доменных событий, `PaymentAuthorization` остаётся нетронутым, так что
существующий HTTP-путь продолжает вести себя ровно как раньше."""

import uuid

from kernel_platform.commands import Command
from kernel_platform.security import Actor, ActorRole
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.authorize_payment import (
    AuthorizePaymentCommand,
    AuthorizePaymentCommandHandler,
)
from core.psp import build_psp_client
from core.settings import settings
from infrastructure.db.unit_of_work import PaymentCommandUnitOfWork

# Синтетический actor для message-driven вызовов (архитектурный бриф D4):
# `AuthorizePaymentCommand`/`VoidPaymentCommand` требуют `actor: Actor`,
# используемый только для логирования (issue #368) — ни один из двух
# хендлеров не проверяет роль. Nil-UUID узнаваем в логах как «не человек».
_SYSTEM_ACTOR = Actor(id=uuid.UUID(int=0), role=ActorRole.USER)


async def handle_authorize_command(session: AsyncSession, command: Command) -> None:
    payload = command.payload
    uow = PaymentCommandUnitOfWork(session)
    handler = AuthorizePaymentCommandHandler(uow, build_psp_client(settings))
    await handler.execute(
        AuthorizePaymentCommand(
            actor=_SYSTEM_ACTOR,
            idempotency_key=str(command.command_id),
            amount=int(payload["amount"]),
            payment_method_token=str(payload["payment_method_token"]),
        )
    )
    # Result -> outbox-факт маппинг (D2/D7) — Seams for TDD #4,
    # tests/unit/test_handle_authorize_command.py.
    raise NotImplementedError("authorize result-to-outbox mapping lands in seam 4")

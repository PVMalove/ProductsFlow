import uuid
from typing import Annotated

from fastapi import APIRouter, Header, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_result
from kernel_platform.security import Actor, ActorRole

from api.dependencies import (
    AuthorizePaymentDI,
    CapturePaymentDI,
    LookupPaymentDI,
    VoidPaymentDI,
)
from api.schemas import AuthorizePaymentRequest, to_capture_command, to_void_command
from application.queries import LookupPaymentQuery
from contracts.payment import PaymentAuthorizationView
from infrastructure.security.auth import RequiredAuth

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

IdempotencyKeyHeader = Annotated[str, Header(alias="Idempotency-Key")]


def _actor(auth: RequiredAuth) -> Actor:
    # payment-service допускает любого аутентифицированного пользователя ко
    # всем 4 операциям — роль не проверяется (архитектурный бриф D6).
    return Actor(id=auth.user_id, role=ActorRole.USER)


@router.post(
    "/authorizations",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_201_CREATED,
)
async def authorize_payment(
    request: AuthorizePaymentRequest,
    idempotency_key: IdempotencyKeyHeader,
    auth: RequiredAuth,
    handler: AuthorizePaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    command = request.to_command(idempotency_key=idempotency_key, actor=_actor(auth))
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_created(result)


@router.post(
    "/authorizations/{authorization_id}/void",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def void_payment(
    authorization_id: uuid.UUID,
    idempotency_key: IdempotencyKeyHeader,
    auth: RequiredAuth,
    handler: VoidPaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    command = to_void_command(
        authorization_id=authorization_id,
        idempotency_key=idempotency_key,
        actor=_actor(auth),
    )
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_result(result)


@router.post(
    "/authorizations/{authorization_id}/capture",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def capture_payment(
    authorization_id: uuid.UUID,
    idempotency_key: IdempotencyKeyHeader,
    auth: RequiredAuth,
    handler: CapturePaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    command = to_capture_command(
        authorization_id=authorization_id,
        idempotency_key=idempotency_key,
        actor=_actor(auth),
    )
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_result(result)


@router.get(
    "/lookup/{idempotency_key}",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def lookup_payment(
    idempotency_key: str,
    auth: RequiredAuth,
    handler: LookupPaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    del (
        auth
    )  # RequiredAuth (архитектурный бриф D6) — любой аутентифицированный пользователь.
    result: Result[PaymentAuthorizationView] = await handler.execute(
        LookupPaymentQuery(idempotency_key=idempotency_key)
    )
    return match_result(result)

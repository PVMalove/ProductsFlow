from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_result
from kernel_platform.security import Actor, ActorRole

from api.http.dependencies import (
    AuthorizePaymentDI,
    CapturePaymentDI,
    LookupPaymentDI,
    VoidPaymentDI,
)
from api.http.schemas import (
    AuthorizePaymentRequest,
    CapturePaymentRequest,
    LookupPaymentRequest,
    VoidPaymentRequest,
)
from application.commands import (
    AuthorizePaymentCommand,
    CapturePaymentCommand,
    VoidPaymentCommand,
)
from application.queries import LookupPaymentQuery
from contracts.payment import PaymentAuthorizationView
from infrastructure.security.auth import RequiredAuth

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

IdempotencyKeyHeader = Annotated[str, Header(alias="Idempotency-Key")]


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
    command: AuthorizePaymentCommand = request.to_command(
        idempotency_key=idempotency_key, actor=_actor(auth)
    )
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_created(result)


@router.post(
    "/authorizations/{authorization_id}/void",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def void_payment(
    request: Annotated[VoidPaymentRequest, Depends()],
    auth: RequiredAuth,
    handler: VoidPaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    command: VoidPaymentCommand = request.to_command(actor=_actor(auth))
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_result(result)


@router.post(
    "/authorizations/{authorization_id}/capture",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def capture_payment(
    request: Annotated[CapturePaymentRequest, Depends()],
    auth: RequiredAuth,
    handler: CapturePaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    command: CapturePaymentCommand = request.to_command(actor=_actor(auth))
    result: Result[PaymentAuthorizationView] = await handler.execute(command)
    return match_result(result)


@router.get(
    "/lookup/{idempotency_key}",
    response_model=ApiResponse[PaymentAuthorizationView],
    status_code=status.HTTP_200_OK,
)
async def lookup_payment(
    request: Annotated[LookupPaymentRequest, Depends()],
    _auth: RequiredAuth,
    handler: LookupPaymentDI,
) -> ApiResponse[PaymentAuthorizationView]:
    query: LookupPaymentQuery = request.to_query()
    result: Result[PaymentAuthorizationView] = await handler.execute(query)
    return match_result(result)


def _actor(auth: RequiredAuth) -> Actor:
    # payment-service допускает любого аутентифицированного пользователя ко
    # всем 4 операциям — роль не проверяется (архитектурный бриф D6).
    return Actor(id=auth.user_id, role=ActorRole.USER)

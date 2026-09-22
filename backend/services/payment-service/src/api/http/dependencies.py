from typing import Annotated

from fastapi import Depends, Request

from application.commands import (
    AuthorizePaymentCommandHandler,
    CapturePaymentCommandHandler,
    VoidPaymentCommandHandler,
)
from application.queries import LookupPaymentQueryHandler
from domain.psp_client import PspClient
from domain.repositories import PaymentAuthorizationRepository
from domain.unit_of_work import PaymentUnitOfWork
from infrastructure.db.payment_repository import (
    PaymentAuthorizationRepository as SqlPaymentAuthorizationRepository,
)
from infrastructure.db.session import DbSessionDI
from infrastructure.db.unit_of_work import SqlPaymentUnitOfWork


def get_payment_uow(session: DbSessionDI) -> PaymentUnitOfWork:
    return SqlPaymentUnitOfWork(session)


PaymentUnitOfWorkDI = Annotated[PaymentUnitOfWork, Depends(get_payment_uow)]


def get_payment_repository(session: DbSessionDI) -> PaymentAuthorizationRepository:
    return SqlPaymentAuthorizationRepository(session)


PaymentAuthorizationRepositoryDI = Annotated[
    PaymentAuthorizationRepository, Depends(get_payment_repository)
]


def get_psp_client(request: Request) -> PspClient:
    client: PspClient = request.app.state.psp_client
    return client


PspClientDI = Annotated[PspClient, Depends(get_psp_client)]


def get_authorize_payment_handler(
    uow: PaymentUnitOfWorkDI, psp_client: PspClientDI
) -> AuthorizePaymentCommandHandler:
    return AuthorizePaymentCommandHandler(uow, psp_client)


AuthorizePaymentDI = Annotated[
    AuthorizePaymentCommandHandler, Depends(get_authorize_payment_handler)
]


def get_void_payment_handler(uow: PaymentUnitOfWorkDI) -> VoidPaymentCommandHandler:
    return VoidPaymentCommandHandler(uow)


VoidPaymentDI = Annotated[VoidPaymentCommandHandler, Depends(get_void_payment_handler)]


def get_capture_payment_handler(
    uow: PaymentUnitOfWorkDI, psp_client: PspClientDI
) -> CapturePaymentCommandHandler:
    return CapturePaymentCommandHandler(uow, psp_client)


CapturePaymentDI = Annotated[
    CapturePaymentCommandHandler, Depends(get_capture_payment_handler)
]


def get_lookup_payment_handler(
    repository: PaymentAuthorizationRepositoryDI,
) -> LookupPaymentQueryHandler:
    return LookupPaymentQueryHandler(repository)


LookupPaymentDI = Annotated[
    LookupPaymentQueryHandler, Depends(get_lookup_payment_handler)
]


__all__ = [
    "AuthorizePaymentDI",
    "CapturePaymentDI",
    "LookupPaymentDI",
    "PaymentAuthorizationRepositoryDI",
    "PaymentUnitOfWorkDI",
    "PspClientDI",
    "VoidPaymentDI",
    "get_authorize_payment_handler",
    "get_capture_payment_handler",
    "get_lookup_payment_handler",
    "get_payment_repository",
    "get_payment_uow",
    "get_psp_client",
    "get_void_payment_handler",
]

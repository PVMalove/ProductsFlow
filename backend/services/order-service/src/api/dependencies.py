from typing import Annotated

from fastapi import Depends

from application.commands import (
    AddCartLineCommandHandler,
    RemoveCartLineCommandHandler,
    UpdateCartLineQuantityCommandHandler,
)
from application.queries import GetCartQueryHandler
from domain.repositories import CartRepository
from domain.unit_of_work import CartUnitOfWork
from infrastructure.db.cart_repository import CartRepository as SqlCartRepository
from infrastructure.db.session import DbSessionDI
from infrastructure.db.unit_of_work import SqlCartUnitOfWork


def get_cart_uow(session: DbSessionDI) -> CartUnitOfWork:
    return SqlCartUnitOfWork(session)


CartUnitOfWorkDI = Annotated[CartUnitOfWork, Depends(get_cart_uow)]


def get_cart_repository(session: DbSessionDI) -> CartRepository:
    return SqlCartRepository(session)


CartRepositoryDI = Annotated[CartRepository, Depends(get_cart_repository)]


def get_add_cart_line_handler(uow: CartUnitOfWorkDI) -> AddCartLineCommandHandler:
    return AddCartLineCommandHandler(uow)


AddCartLineDI = Annotated[
    AddCartLineCommandHandler, Depends(get_add_cart_line_handler)
]


def get_update_cart_line_quantity_handler(
    uow: CartUnitOfWorkDI,
) -> UpdateCartLineQuantityCommandHandler:
    return UpdateCartLineQuantityCommandHandler(uow)


UpdateCartLineQuantityDI = Annotated[
    UpdateCartLineQuantityCommandHandler,
    Depends(get_update_cart_line_quantity_handler),
]


def get_remove_cart_line_handler(uow: CartUnitOfWorkDI) -> RemoveCartLineCommandHandler:
    return RemoveCartLineCommandHandler(uow)


RemoveCartLineDI = Annotated[
    RemoveCartLineCommandHandler, Depends(get_remove_cart_line_handler)
]


def get_get_cart_handler(repository: CartRepositoryDI) -> GetCartQueryHandler:
    return GetCartQueryHandler(repository)


GetCartDI = Annotated[GetCartQueryHandler, Depends(get_get_cart_handler)]


__all__ = [
    "AddCartLineDI",
    "CartRepositoryDI",
    "CartUnitOfWorkDI",
    "GetCartDI",
    "RemoveCartLineDI",
    "UpdateCartLineQuantityDI",
    "get_add_cart_line_handler",
    "get_cart_repository",
    "get_cart_uow",
    "get_get_cart_handler",
    "get_remove_cart_line_handler",
    "get_update_cart_line_quantity_handler",
]

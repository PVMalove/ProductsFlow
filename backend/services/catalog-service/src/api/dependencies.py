from typing import Annotated

from fastapi import Depends

from application.commands import (
    ActivateProductCommandHandler,
    CreateProductCommandHandler,
    DeactivateProductCommandHandler,
    DeleteProductCommandHandler,
    DeleteProductImageCommandHandler,
    UpdateProductCommandHandler,
    UpsertProductImageCommandHandler,
)
from application.ports import (
    Actor,
    OwnerReadModel,
    ProductAuditReader,
)
from application.ports import (
    IdentityGateway as ApplicationIdentityGateway,
)
from application.queries import (
    GetProductAuditQueryHandler,
    GetProductImageQueryHandler,
    GetProductQueryHandler,
    ListProductsQueryHandler,
)
from core.settings import settings
from domain.repositories import ProductRepository
from domain.unit_of_work import CatalogUnitOfWork
from infrastructure.db.audit import SqlProductAuditReader
from infrastructure.db.owner_read_model import SqlOwnerReadModel
from infrastructure.db.product_repository import (
    ProductRepository as SqlProductRepository,
)
from infrastructure.db.session import DbSessionDI
from infrastructure.db.unit_of_work import SqlCatalogUnitOfWork
from infrastructure.identity_gateway import IdentityGatewayAdapter
from infrastructure.security.auth import (
    AuthContext,
    IdentityGatewayDI,
    OptionalAuth,
    RequiredAuth,
)
from infrastructure.storage import StorageDI


def get_product_repository(session: DbSessionDI) -> ProductRepository:
    return SqlProductRepository(session)


ProductRepositoryDI = Annotated[ProductRepository, Depends(get_product_repository)]


def get_catalog_uow(session: DbSessionDI) -> CatalogUnitOfWork:
    return SqlCatalogUnitOfWork(session)


CatalogUnitOfWorkDI = Annotated[CatalogUnitOfWork, Depends(get_catalog_uow)]


def get_owner_read_model(session: DbSessionDI) -> OwnerReadModel:
    return SqlOwnerReadModel(session)


OwnerReadModelDI = Annotated[OwnerReadModel, Depends(get_owner_read_model)]


def get_product_audit_reader(session: DbSessionDI) -> ProductAuditReader:
    return SqlProductAuditReader(session)


ProductAuditReaderDI = Annotated[ProductAuditReader, Depends(get_product_audit_reader)]


def to_actor(auth: AuthContext) -> Actor:
    return Actor(user_id=auth.user_id, token=auth.token)


def get_application_identity_gateway(
    identity: IdentityGatewayDI,
) -> ApplicationIdentityGateway:
    return IdentityGatewayAdapter(identity)


ApplicationIdentityGatewayDI = Annotated[
    ApplicationIdentityGateway, Depends(get_application_identity_gateway)
]


def get_create_product_handler(
    uow: CatalogUnitOfWorkDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
) -> CreateProductCommandHandler:
    return CreateProductCommandHandler(uow, owner_read_model, identity)


CreateProductDI = Annotated[
    CreateProductCommandHandler, Depends(get_create_product_handler)
]


def get_list_products_handler(
    repository: ProductRepositoryDI,
) -> ListProductsQueryHandler:
    return ListProductsQueryHandler(repository)


ListProductsDI = Annotated[ListProductsQueryHandler, Depends(get_list_products_handler)]


def get_product_handler(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProductQueryHandler:
    return GetProductQueryHandler(repository, owner_read_model, identity)


GetProductDI = Annotated[GetProductQueryHandler, Depends(get_product_handler)]


def get_update_product_handler(
    uow: CatalogUnitOfWorkDI, identity: ApplicationIdentityGatewayDI
) -> UpdateProductCommandHandler:
    return UpdateProductCommandHandler(uow, identity)


UpdateProductDI = Annotated[
    UpdateProductCommandHandler, Depends(get_update_product_handler)
]


def get_activate_product_handler(
    uow: CatalogUnitOfWorkDI, identity: ApplicationIdentityGatewayDI
) -> ActivateProductCommandHandler:
    return ActivateProductCommandHandler(uow, identity)


ActivateProductDI = Annotated[
    ActivateProductCommandHandler, Depends(get_activate_product_handler)
]


def get_deactivate_product_handler(
    uow: CatalogUnitOfWorkDI, identity: ApplicationIdentityGatewayDI
) -> DeactivateProductCommandHandler:
    return DeactivateProductCommandHandler(uow, identity)


DeactivateProductDI = Annotated[
    DeactivateProductCommandHandler, Depends(get_deactivate_product_handler)
]


def get_delete_product_handler(
    uow: CatalogUnitOfWorkDI, identity: ApplicationIdentityGatewayDI
) -> DeleteProductCommandHandler:
    return DeleteProductCommandHandler(uow, identity)


DeleteProductDI = Annotated[
    DeleteProductCommandHandler, Depends(get_delete_product_handler)
]


def get_product_audit_handler(
    repository: ProductRepositoryDI,
    audit_reader: ProductAuditReaderDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProductAuditQueryHandler:
    return GetProductAuditQueryHandler(repository, audit_reader, identity)


GetProductAuditDI = Annotated[
    GetProductAuditQueryHandler, Depends(get_product_audit_handler)
]


def get_product_image_handler(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> GetProductImageQueryHandler:
    return GetProductImageQueryHandler(
        repository,
        owner_read_model,
        identity,
        storage,
        settings.minio_bucket_name_product,
    )


GetProductImageDI = Annotated[
    GetProductImageQueryHandler, Depends(get_product_image_handler)
]


def get_upsert_product_image_handler(
    uow: CatalogUnitOfWorkDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> UpsertProductImageCommandHandler:
    return UpsertProductImageCommandHandler(
        uow, identity, storage, settings.minio_bucket_name_product
    )


UpsertProductImageDI = Annotated[
    UpsertProductImageCommandHandler, Depends(get_upsert_product_image_handler)
]


def get_delete_product_image_handler(
    uow: CatalogUnitOfWorkDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> DeleteProductImageCommandHandler:
    return DeleteProductImageCommandHandler(
        uow, identity, storage, settings.minio_bucket_name_product
    )


DeleteProductImageDI = Annotated[
    DeleteProductImageCommandHandler, Depends(get_delete_product_image_handler)
]


__all__ = [
    "ActivateProductDI",
    "CreateProductDI",
    "DeactivateProductDI",
    "DeleteProductDI",
    "GetProductAuditDI",
    "GetProductDI",
    "GetProductImageDI",
    "DeleteProductImageDI",
    "ApplicationIdentityGatewayDI",
    "CatalogUnitOfWorkDI",
    "IdentityGatewayDI",
    "ListProductsDI",
    "OptionalAuth",
    "RequiredAuth",
    "UpdateProductDI",
    "UpsertProductImageDI",
    "to_actor",
]

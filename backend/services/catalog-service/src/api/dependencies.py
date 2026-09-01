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
from infrastructure.db.audit import SqlProductAuditReader
from infrastructure.db.owner_read_model import SqlOwnerReadModel
from infrastructure.db.product_repository import (
    ProductRepository as SqlProductRepository,
)
from infrastructure.db.session import DbSessionDI
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


def get_create_product_use_case(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
) -> CreateProductCommandHandler:
    return CreateProductCommandHandler(repository, owner_read_model, identity)


CreateProductDI = Annotated[
    CreateProductCommandHandler, Depends(get_create_product_use_case)
]


def get_list_products_use_case(
    repository: ProductRepositoryDI,
) -> ListProductsQueryHandler:
    return ListProductsQueryHandler(repository)


ListProductsDI = Annotated[
    ListProductsQueryHandler, Depends(get_list_products_use_case)
]


def get_product_use_case(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProductQueryHandler:
    return GetProductQueryHandler(repository, owner_read_model, identity)


GetProductDI = Annotated[GetProductQueryHandler, Depends(get_product_use_case)]


def get_update_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> UpdateProductCommandHandler:
    return UpdateProductCommandHandler(repository, identity)


UpdateProductDI = Annotated[
    UpdateProductCommandHandler, Depends(get_update_product_use_case)
]


def get_activate_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> ActivateProductCommandHandler:
    return ActivateProductCommandHandler(repository, identity)


ActivateProductDI = Annotated[
    ActivateProductCommandHandler, Depends(get_activate_product_use_case)
]


def get_deactivate_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> DeactivateProductCommandHandler:
    return DeactivateProductCommandHandler(repository, identity)


DeactivateProductDI = Annotated[
    DeactivateProductCommandHandler, Depends(get_deactivate_product_use_case)
]


def get_delete_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> DeleteProductCommandHandler:
    return DeleteProductCommandHandler(repository, identity)


DeleteProductDI = Annotated[
    DeleteProductCommandHandler, Depends(get_delete_product_use_case)
]


def get_product_audit_use_case(
    repository: ProductRepositoryDI,
    audit_reader: ProductAuditReaderDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProductAuditQueryHandler:
    return GetProductAuditQueryHandler(repository, audit_reader, identity)


GetProductAuditDI = Annotated[
    GetProductAuditQueryHandler, Depends(get_product_audit_use_case)
]


def get_product_image_use_case(
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
    GetProductImageQueryHandler, Depends(get_product_image_use_case)
]


def get_upsert_product_image_use_case(
    repository: ProductRepositoryDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> UpsertProductImageCommandHandler:
    return UpsertProductImageCommandHandler(
        repository, identity, storage, settings.minio_bucket_name_product
    )


UpsertProductImageDI = Annotated[
    UpsertProductImageCommandHandler, Depends(get_upsert_product_image_use_case)
]


def get_delete_product_image_use_case(
    repository: ProductRepositoryDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> DeleteProductImageCommandHandler:
    return DeleteProductImageCommandHandler(
        repository, identity, storage, settings.minio_bucket_name_product
    )


DeleteProductImageDI = Annotated[
    DeleteProductImageCommandHandler, Depends(get_delete_product_image_use_case)
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
    "IdentityGatewayDI",
    "ListProductsDI",
    "OptionalAuth",
    "RequiredAuth",
    "UpdateProductDI",
    "UpsertProductImageDI",
    "to_actor",
]

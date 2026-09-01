from typing import Annotated

from fastapi import Depends

from application.ports import (
    Actor,
    OwnerReadModel,
    ProductAuditReader,
)
from application.ports import (
    IdentityGateway as ApplicationIdentityGateway,
)
from application.product_image_use_cases import (
    DeleteProductImage,
    GetProductImage,
    UpsertProductImage,
)
from application.product_use_cases import (
    ActivateProduct,
    CreateProduct,
    DeactivateProduct,
    DeleteProduct,
    GetProduct,
    GetProductAudit,
    ListProducts,
    UpdateProduct,
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
) -> CreateProduct:
    return CreateProduct(repository, owner_read_model, identity)


CreateProductDI = Annotated[CreateProduct, Depends(get_create_product_use_case)]


def get_list_products_use_case(repository: ProductRepositoryDI) -> ListProducts:
    return ListProducts(repository)


ListProductsDI = Annotated[ListProducts, Depends(get_list_products_use_case)]


def get_product_use_case(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProduct:
    return GetProduct(repository, owner_read_model, identity)


GetProductDI = Annotated[GetProduct, Depends(get_product_use_case)]


def get_update_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> UpdateProduct:
    return UpdateProduct(repository, identity)


UpdateProductDI = Annotated[UpdateProduct, Depends(get_update_product_use_case)]


def get_activate_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> ActivateProduct:
    return ActivateProduct(repository, identity)


ActivateProductDI = Annotated[ActivateProduct, Depends(get_activate_product_use_case)]


def get_deactivate_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> DeactivateProduct:
    return DeactivateProduct(repository, identity)


DeactivateProductDI = Annotated[
    DeactivateProduct, Depends(get_deactivate_product_use_case)
]


def get_delete_product_use_case(
    repository: ProductRepositoryDI, identity: ApplicationIdentityGatewayDI
) -> DeleteProduct:
    return DeleteProduct(repository, identity)


DeleteProductDI = Annotated[DeleteProduct, Depends(get_delete_product_use_case)]


def get_product_audit_use_case(
    repository: ProductRepositoryDI,
    audit_reader: ProductAuditReaderDI,
    identity: ApplicationIdentityGatewayDI,
) -> GetProductAudit:
    return GetProductAudit(repository, audit_reader, identity)


GetProductAuditDI = Annotated[GetProductAudit, Depends(get_product_audit_use_case)]


def get_product_image_use_case(
    repository: ProductRepositoryDI,
    owner_read_model: OwnerReadModelDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> GetProductImage:
    return GetProductImage(
        repository,
        owner_read_model,
        identity,
        storage,
        settings.minio_bucket_name_product,
    )


GetProductImageDI = Annotated[GetProductImage, Depends(get_product_image_use_case)]


def get_upsert_product_image_use_case(
    repository: ProductRepositoryDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> UpsertProductImage:
    return UpsertProductImage(
        repository, identity, storage, settings.minio_bucket_name_product
    )


UpsertProductImageDI = Annotated[
    UpsertProductImage, Depends(get_upsert_product_image_use_case)
]


def get_delete_product_image_use_case(
    repository: ProductRepositoryDI,
    identity: ApplicationIdentityGatewayDI,
    storage: StorageDI,
) -> DeleteProductImage:
    return DeleteProductImage(
        repository, identity, storage, settings.minio_bucket_name_product
    )


DeleteProductImageDI = Annotated[
    DeleteProductImage, Depends(get_delete_product_image_use_case)
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

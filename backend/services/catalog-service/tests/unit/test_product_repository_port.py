from domain.repositories import ProductRepository
from infrastructure.db.product_repository import (
    ProductRepository as ProductRepositoryImplementation,
)


def test_product_repository_implements_domain_contract() -> None:
    repository = object.__new__(ProductRepositoryImplementation)

    assert isinstance(repository, ProductRepository)

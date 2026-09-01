from application.ports.product_repository import ProductRepository
from infrastructure.db.product_repository import SqlAlchemyProductRepository


def test_sqlalchemy_repository_implements_application_port() -> None:
    repository = object.__new__(SqlAlchemyProductRepository)

    assert isinstance(repository, ProductRepository)

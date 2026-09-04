from domain.repositories import UserRepository
from infrastructure.db.user_repository import (
    UserRepository as UserRepositoryImplementation,
)


def test_user_repository_implements_domain_contract() -> None:
    repository = object.__new__(UserRepositoryImplementation)

    assert isinstance(repository, UserRepository)

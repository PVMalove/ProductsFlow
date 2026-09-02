import uuid

import pytest

from api.bootstrap import wait_for_admin_user_id
from api.seed_factories import generate_products
from application.ports import OwnerSnapshot

ADMIN_ID = uuid.uuid4()


class FakeAdminReadModel:
    """Fake read port (prior art: identity-service's
    tests/unit/fake_user_repository.py) — returns `None` for a fixed number
    of polls, then the admin snapshot, so `wait_for_admin_user_id` can be
    unit-tested without a real database or event consumer."""

    def __init__(self, *, polls_until_found: int) -> None:
        self._polls_until_found = polls_until_found
        self.calls = 0

    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None:
        raise NotImplementedError

    async def upsert(self, owner: OwnerSnapshot) -> None:
        raise NotImplementedError

    async def find_by_role(self, role: str) -> OwnerSnapshot | None:
        assert role == "admin"
        self.calls += 1
        if self.calls < self._polls_until_found:
            return None
        return OwnerSnapshot(
            user_id=ADMIN_ID, role="admin", is_active=True, last_applied_outbox_id=1
        )


class NeverFoundReadModel:
    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None:
        raise NotImplementedError

    async def upsert(self, owner: OwnerSnapshot) -> None:
        raise NotImplementedError

    async def find_by_role(self, role: str) -> OwnerSnapshot | None:
        return None


@pytest.mark.asyncio
async def test_wait_for_admin_user_id_returns_id_once_row_appears() -> None:
    read_model = FakeAdminReadModel(polls_until_found=3)

    user_id = await wait_for_admin_user_id(
        read_model, timeout_seconds=5.0, poll_interval_seconds=0.0
    )

    assert user_id == ADMIN_ID
    assert read_model.calls == 3


@pytest.mark.asyncio
async def test_wait_for_admin_user_id_raises_when_row_never_appears() -> None:
    with pytest.raises(RuntimeError, match="no OwnerReadModel row"):
        await wait_for_admin_user_id(
            NeverFoundReadModel(), timeout_seconds=0.05, poll_interval_seconds=0.01
        )


def test_generate_products_is_deterministic_and_produces_unique_names() -> None:
    products = generate_products(360)
    products_again = generate_products(360)

    assert len(products) == 360
    assert len({product.name for product in products}) == 360
    assert products == products_again
    assert products[0].name == "Компактный лейка"
    assert products[0].category == "Дом и сад"
    assert products[-1].name == "Прочный наушники"

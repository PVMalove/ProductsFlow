"""Сквозной HTTP через реальный Postgres (issue #367, Seams for TDD #8, по
образцу support's test_support_api.py): 200 для admin, 403 для не-admin,
401 без токена, audit-строка действительно создана."""

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.audit import InventoryAuditLog
from infrastructure.db.entity_configurations.models import InventoryModel
from tests.integration.fake_identity_client import FakeIdentityClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_zero_inventory(db_session: AsyncSession, product_id: uuid.UUID) -> None:
    db_session.add(InventoryModel(product_id=product_id, quantity=0))
    await db_session.flush()


async def test_adjust_inventory_stock_requires_authentication(
    inventory_client: httpx.AsyncClient,
) -> None:
    response = await inventory_client.post(
        f"/api/v1/inventory/{uuid.uuid4()}/adjustments",
        json={"delta": 1, "reason": "?"},
    )

    assert response.status_code == 401


async def test_adjust_inventory_stock_rejects_non_admin(
    inventory_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    product_id = uuid.uuid4()
    await _seed_zero_inventory(db_session, product_id)
    identity_client.register("user-token", user_id=uuid.uuid4(), role="user")

    response = await inventory_client.post(
        f"/api/v1/inventory/{product_id}/adjustments",
        json={"delta": 5, "reason": "приход"},
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 403


async def test_adjust_inventory_stock_fails_closed_when_identity_unavailable(
    inventory_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    product_id = uuid.uuid4()
    await _seed_zero_inventory(db_session, product_id)
    identity_client.register("admin-token", user_id=uuid.uuid4(), role="admin")
    identity_client.unavailable = True

    response = await inventory_client.post(
        f"/api/v1/inventory/{product_id}/adjustments",
        json={"delta": 5, "reason": "приход"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 503


async def test_adjust_inventory_stock_succeeds_for_admin_and_writes_audit_row(
    inventory_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    product_id = uuid.uuid4()
    await _seed_zero_inventory(db_session, product_id)
    identity_client.register("admin-token", user_id=uuid.uuid4(), role="admin")

    response = await inventory_client.post(
        f"/api/v1/inventory/{product_id}/adjustments",
        json={"delta": 5, "reason": "приход"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["quantity"] == 5
    assert body["data"]["product_id"] == str(product_id)

    audit_rows = (
        await db_session.scalars(
            select(InventoryAuditLog).where(InventoryAuditLog.product_id == product_id)
        )
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "adjusted"


async def test_adjust_inventory_stock_rejects_negative_result_as_conflict(
    inventory_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
    db_session: AsyncSession,
) -> None:
    product_id = uuid.uuid4()
    await _seed_zero_inventory(db_session, product_id)
    identity_client.register("admin-token", user_id=uuid.uuid4(), role="admin")

    response = await inventory_client.post(
        f"/api/v1/inventory/{product_id}/adjustments",
        json={"delta": -1, "reason": "недостача"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "negative_stock_adjustment"


async def test_adjust_inventory_stock_returns_404_for_unknown_product(
    inventory_client: httpx.AsyncClient,
    identity_client: FakeIdentityClient,
) -> None:
    identity_client.register("admin-token", user_id=uuid.uuid4(), role="admin")

    response = await inventory_client.post(
        f"/api/v1/inventory/{uuid.uuid4()}/adjustments",
        json={"delta": 1, "reason": "?"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 404

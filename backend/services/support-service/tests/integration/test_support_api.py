"""HTTP contract tests for the support service (ADR 0033)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from kernel_platform.outbox.models import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from api.main import app
from core.settings import settings
from infrastructure.db.session import get_db_session
from infrastructure.db.user_projection import UserProjectionRow

pytestmark = pytest.mark.asyncio(loop_scope="session")

ISSUER = "identity-service"


@pytest.fixture(scope="module")
def _keys() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture
def support_private_key(
    _keys: tuple[bytes, bytes], monkeypatch: pytest.MonkeyPatch
) -> bytes:
    private_pem, public_pem = _keys
    monkeypatch.setattr(settings, "support_jwt_public_key", public_pem.decode())
    return private_pem


def _token(private_pem: bytes, user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "iss": ISSUER,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _api_schema(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with db_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def support_api_client(
    db_session: AsyncSession, support_private_key: bytes, _api_schema: None
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://support"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_support_http_flow_covers_tickets_and_actor_states(
    support_api_client: httpx.AsyncClient,
    support_private_key: bytes,
    db_session: AsyncSession,
) -> None:
    client = support_api_client
    private_pem = support_private_key
    user_id = uuid4()
    admin_id = uuid4()

    unknown_actor = await client.get(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {_token(private_pem, user_id)}"},
    )
    assert unknown_actor.status_code == 401
    assert unknown_actor.json()["error"]["code"] == "UNAUTHORIZED"

    db_session.add(
        UserProjectionRow(
            user_id=user_id,
            role="user",
            is_active=True,
            deleted=False,
            last_applied_outbox_id=1,
        )
    )
    db_session.add(
        UserProjectionRow(
            user_id=admin_id,
            role="admin",
            is_active=True,
            deleted=False,
            last_applied_outbox_id=1,
        )
    )
    await db_session.commit()

    user_headers = {"Authorization": f"Bearer {_token(private_pem, user_id)}"}
    admin_headers = {"Authorization": f"Bearer {_token(private_pem, admin_id)}"}

    created = await client.post(
        "/api/v1/tickets",
        headers=user_headers,
        json={"subject": "Help", "first_message": "Need help"},
    )
    assert created.status_code == 201
    ticket = created.json()["data"]
    assert created.json()["meta"] == {}
    assert ticket["messages"][0]["body"] == "Need help"
    ticket_id = ticket["id"]

    listing = await client.get("/api/v1/tickets", headers=user_headers)
    assert listing.status_code == 200
    assert listing.json()["data"][0]["id"] == ticket_id
    assert "next_cursor" in listing.json()["meta"]

    detail = await client.get(f"/api/v1/tickets/{ticket_id}", headers=user_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["subject"] == "Help"
    assert detail.json()["meta"]["has_more"] is False

    admin_sees_the_ticket = await client.get(
        f"/api/v1/tickets/{ticket_id}", headers=admin_headers
    )
    assert admin_sees_the_ticket.status_code == 200

    added = await client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=admin_headers,
        json={"body": "How can we help?"},
    )
    assert added.status_code == 201
    assert added.json()["data"]["status"] == "OPEN"

    changed = await client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=admin_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["status"] == "IN_PROGRESS"

    forbidden_status_change = await client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=user_headers,
        json={"status": "RESOLVED"},
    )
    assert forbidden_status_change.status_code == 403
    assert forbidden_status_change.json()["error"]["code"] == "FORBIDDEN"

    detail_after = await client.get(
        f"/api/v1/tickets/{ticket_id}", headers=user_headers
    )
    message_id = detail_after.json()["data"]["messages"][-1]["id"]

    deleted = await client.delete(
        f"/api/v1/tickets/{ticket_id}/messages/{message_id}", headers=admin_headers
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"data": None, "meta": {}}

    forbidden_admin_route = await client.get(
        "/api/v1/tickets/admin", headers=user_headers
    )
    assert forbidden_admin_route.status_code == 403
    assert forbidden_admin_route.json()["error"]["code"] == "FORBIDDEN"

    admin_detail = await client.get(
        f"/api/v1/tickets/admin/{ticket_id}", headers=admin_headers
    )
    assert admin_detail.status_code == 200
    assert admin_detail.json()["data"]["id"] == ticket_id

    forbidden_admin_detail = await client.get(
        f"/api/v1/tickets/admin/{ticket_id}", headers=user_headers
    )
    assert forbidden_admin_detail.status_code == 403
    assert forbidden_admin_detail.json()["error"]["code"] == "FORBIDDEN"

    row = await db_session.get(UserProjectionRow, user_id)
    assert row is not None
    row.is_active = False
    await db_session.commit()

    deactivated = await client.get("/api/v1/tickets", headers=user_headers)
    assert deactivated.status_code == 403
    assert deactivated.json()["error"]["code"] == "FORBIDDEN"

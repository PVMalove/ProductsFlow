"""HTTP contract tests for the identity service."""

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import jwt
import pytest
import pytest_asyncio
from kernel_platform.outbox.models import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from api.main import app
from core.settings import settings
from domain.role import Role
from domain.user_id import UserId
from infrastructure.db import audit as _audit  # noqa: F401
from infrastructure.db import models as _models  # noqa: F401
from infrastructure.db.session import get_db_session
from infrastructure.db.unit_of_work import SqlIdentityUnitOfWork
from infrastructure.db.user_repository import UserRepository
from tests.unit.keygen import write_rsa_key_file

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def api_key_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    key_path = tmp_path / "identity-api.pem"
    write_rsa_key_file(key_path)
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", str(key_path))
    return key_path


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
async def identity_api_client(
    db_session: AsyncSession, api_key_path: Path, _api_schema: None
) -> AsyncIterator[httpx.AsyncClient]:
    assert api_key_path.is_file()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://identity"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_identity_http_flow_covers_auth_users_and_audit(
    identity_api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    client = identity_api_client

    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "Password1"},
    )
    assert registered.status_code == 201
    user = registered.json()["data"]
    assert registered.json()["meta"] == {}
    assert UUID(user["id"])
    assert user["email"] == "user@example.com"
    assert user["role"] == "user"
    assert user["is_active"] is True

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "user@example.com", "password": "Password1"},
    )
    assert login.status_code == 200
    user_token = login.json()["access_token"]
    assert UUID(jwt.decode(user_token, options={"verify_signature": False})["sub"])

    authorized = {"Authorization": f"Bearer {user_token}"}
    me = await client.get("/api/v1/users/me", headers=authorized)
    assert me.status_code == 200
    assert me.json()["data"]["id"] == user["id"]

    changed = await client.patch(
        "/api/v1/users/me/password",
        headers=authorized,
        json={"old_password": "Password1", "new_password": "NewPassword2"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["id"] == user["id"]
    bad_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "user@example.com", "password": "Password1"},
    )
    assert bad_login.status_code == 401

    admin_registration = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "password": "AdminPass1"},
    )
    assert admin_registration.status_code == 201
    admin_id = UUID(admin_registration.json()["data"]["id"])
    admin = await UserRepository(db_session).get_by_id(UserId(admin_id))
    assert admin is not None
    admin.role = Role.ADMIN
    uow = SqlIdentityUnitOfWork(db_session)
    async with uow:
        await uow.users.save(admin)
        await uow.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    deactivated = await client.patch(
        f"/api/v1/users/{user['id']}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["is_active"] is False
    denied_me = await client.get("/api/v1/users/me", headers=authorized)
    assert denied_me.status_code == 403
    assert denied_me.json()["error"]["code"] == "FORBIDDEN"

    activated = await client.patch(
        f"/api/v1/users/{user['id']}/activate", headers=admin_headers
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["is_active"] is True

    listing = await client.get("/api/v1/users/", headers=admin_headers)
    assert listing.status_code == 200
    assert {item["email"] for item in listing.json()["data"]} == {
        "user@example.com",
        "admin@example.com",
    }

    forbidden_listing = await client.get("/api/v1/users/", headers=authorized)
    assert forbidden_listing.status_code == 403
    assert forbidden_listing.json()["error"]["code"] == "FORBIDDEN"

    own_audit = await client.get("/api/v1/users/me/audit", headers=authorized)
    assert own_audit.status_code == 200
    assert own_audit.json()["meta"] == {}
    assert [entry["action"] for entry in own_audit.json()["data"]] == [
        "registered",
        "password_changed",
        "deactivated",
        "activated",
    ]

    target_audit = await client.get(
        f"/api/v1/users/{user['id']}/audit", headers=admin_headers
    )
    assert target_audit.status_code == 200
    assert len(target_audit.json()["data"]) == 4

    missing_target_audit = await client.get(
        f"/api/v1/users/{UUID(int=0)}/audit", headers=admin_headers
    )
    assert missing_target_audit.status_code == 404
    assert missing_target_audit.json()["error"]["code"] == "user_not_found"

    global_audit = await client.get(
        "/api/v1/users/audit?page_index=1&page_size=2", headers=admin_headers
    )
    assert global_audit.status_code == 200
    assert global_audit.json()["meta"]["total"] == 6
    assert global_audit.json()["meta"]["total_pages"] == 3

    self_deactivation = await client.patch(
        f"/api/v1/users/{admin_id}/deactivate", headers=admin_headers
    )
    assert self_deactivation.status_code == 403
    assert self_deactivation.json()["error"]["code"] == "cannot_deactivate_self"

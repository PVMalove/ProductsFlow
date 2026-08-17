import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import UserRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

DEFAULT_PASSWORD = "secret123"


async def _register(
    client: AsyncClient, username: str, password: str = DEFAULT_PASSWORD
) -> Response:
    return await client.post(
        "/auth/register", json={"username": username, "password": password}
    )


async def test_register_then_login_returns_an_access_token(
    client: AsyncClient,
) -> None:
    register_response = await _register(client, "petrov")
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        data={"username": "petrov", "password": DEFAULT_PASSWORD},
    )

    assert login_response.status_code == 200
    body = login_response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_registering_a_taken_username_returns_409(client: AsyncClient) -> None:
    first = await _register(client, "sidorov")
    assert first.status_code == 201

    second = await _register(client, "sidorov")

    assert second.status_code == 409


async def test_registering_with_a_short_username_returns_422_with_a_readable_message(
    client: AsyncClient,
) -> None:
    response = await _register(client, "ab")

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["field"] == "username" for error in errors)
    assert all(error["message"] for error in errors)


async def test_registering_with_a_weak_password_returns_422_with_a_readable_message(
    client: AsyncClient,
) -> None:
    response = await _register(client, "kuznecov", "short")

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["field"] == "password" for error in errors)
    assert all(error["message"] for error in errors)


async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    await _register(client, "morozov")

    response = await client.post(
        "/auth/login", data={"username": "morozov", "password": "wrong-pass1"}
    )

    assert response.status_code == 401


async def test_login_as_a_deactivated_user_returns_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    register_response = await _register(client, "volkov")
    user_id = register_response.json()["id"]
    # Обходим HTTP для деактивации: /users/{id}/deactivate требует AdminUser,
    # а регистрация всегда создаёт роль USER — через чистый HTTP-флоу
    # админ-токен взять неоткуда, поэтому деактивируем напрямую в БД.
    await UserRepository(db_session).set_active_user(user_id, False)

    response = await client.post(
        "/auth/login", data={"username": "volkov", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403

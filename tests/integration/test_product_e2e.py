import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole

pytestmark = pytest.mark.asyncio(loop_scope="session")

DEFAULT_PASSWORD = "secret123"


async def _register_and_login(
    client: AsyncClient, username: str, password: str = DEFAULT_PASSWORD
) -> tuple[int, str]:
    register_response = await client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert register_response.status_code == 201
    user_id = register_response.json()["id"]

    login_response = await client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert login_response.status_code == 200

    return user_id, login_response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _promote_to_admin(session: AsyncSession, user_id: int) -> None:
    # Нет публичного HTTP-пути назначить роль admin (UserCreate её не
    # принимает, seed_db() в тестовом харнессе не запускается) — меняем
    # роль напрямую через ту же сессию, что видит и HTTP-клиент.
    user = await session.get(User, user_id)
    assert user is not None
    user.role = UserRole.ADMIN
    await session.commit()


async def _create_product_via_http(
    client: AsyncClient, token: str, name: str = "Ноутбук"
) -> int:
    response = await client.post(
        "/products/",
        json={
            "name": name,
            "category": "Электроника",
            "price": 1000.0,
            "description": "Тестовый товар",
        },
        headers=_auth(token),
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _audit_actions(client: AsyncClient, token: str, product_id: int) -> list[str]:
    response = await client.get(f"/products/{product_id}/audit", headers=_auth(token))
    assert response.status_code == 200
    return [entry["action"] for entry in response.json()]


async def test_full_product_lifecycle_reflects_in_get_and_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "lifecycle1")

    product_id = await _create_product_via_http(client, owner_token, name="Ноутбук")

    get_response = await client.get(f"/products/{product_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Ноутбук"
    assert await _audit_actions(client, owner_token, product_id) == ["created"]

    update_response = await client.put(
        f"/products/{product_id}", json={"price": 1200.0}, headers=_auth(owner_token)
    )
    assert update_response.status_code == 204

    get_after_update = await client.get(f"/products/{product_id}")
    assert get_after_update.json()["price"] == 1200.0
    assert get_after_update.json()["name"] == "Ноутбук"
    assert await _audit_actions(client, owner_token, product_id) == [
        "created",
        "updated",
    ]

    delete_response = await client.delete(
        f"/products/{product_id}", headers=_auth(owner_token)
    )
    assert delete_response.status_code == 204

    get_after_delete = await client.get(f"/products/{product_id}")
    assert get_after_delete.status_code == 404

    # После удаления продукта get_product_audit_logs (app/router/products.py)
    # больше не пускает обычного владельца к его audit-логу — только админа.
    # Проверяем итоговую DELETED-запись от имени отдельного администратора,
    # а не подменяем весь сценарий на "владелец = админ" с самого начала.
    admin_id, admin_token = await _register_and_login(client, "lifeadmin1")
    await _promote_to_admin(db_session, admin_id)
    assert await _audit_actions(client, admin_token, product_id) == [
        "created",
        "updated",
        "deleted",
    ]


async def test_owner_reading_own_product_audit_twice_in_a_row_is_idempotent(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "reader1")
    product_id = await _create_product_via_http(client, owner_token)

    first = await _audit_actions(client, owner_token, product_id)
    second = await _audit_actions(client, owner_token, product_id)

    assert first == second == ["created"]


async def test_owner_loses_audit_access_after_deleting_their_own_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "deleter1")
    product_id = await _create_product_via_http(client, owner_token)

    delete_response = await client.delete(
        f"/products/{product_id}", headers=_auth(owner_token)
    )
    assert delete_response.status_code == 204

    response = await client.get(
        f"/products/{product_id}/audit", headers=_auth(owner_token)
    )

    assert response.status_code == 403


async def test_non_owner_cannot_read_audit_of_an_existing_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "owner5")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "intruder3")

    response = await client.get(
        f"/products/{product_id}/audit", headers=_auth(intruder_token)
    )

    assert response.status_code == 403


async def test_admin_can_read_audit_of_an_existing_foreign_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "owner6")
    product_id = await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "admin4")
    await _promote_to_admin(db_session, admin_id)

    assert await _audit_actions(client, admin_token, product_id) == ["created"]


async def test_reading_audit_for_a_product_that_never_existed_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # 404 не зависит от роли вызывающего: даже админ, который в остальном
    # обходит проверку владения, получает 404 на id без единой audit-записи
    # (см. else-ветку get_product_audit_logs — роль там вообще не смотрится).
    _, user_token = await _register_and_login(client, "norole1")
    admin_id, admin_token = await _register_and_login(client, "norole2")
    await _promote_to_admin(db_session, admin_id)

    user_response = await client.get(
        "/products/999999/audit", headers=_auth(user_token)
    )
    admin_response = await client.get(
        "/products/999999/audit", headers=_auth(admin_token)
    )

    assert user_response.status_code == 404
    assert admin_response.status_code == 404


async def test_non_owner_without_admin_cannot_update_a_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "owner1")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "intruder1")

    response = await client.put(
        f"/products/{product_id}", json={"price": 1.0}, headers=_auth(intruder_token)
    )

    assert response.status_code == 403


async def test_non_owner_without_admin_cannot_delete_a_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "owner2")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "intruder2")

    response = await client.delete(
        f"/products/{product_id}", headers=_auth(intruder_token)
    )

    assert response.status_code == 403


async def test_regular_user_cannot_list_product_audit(client: AsyncClient) -> None:
    _, token = await _register_and_login(client, "regular1")

    response = await client.get("/products/audit", headers=_auth(token))

    assert response.status_code == 403


async def test_admin_can_update_and_delete_a_foreign_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "owner3")
    product_id = await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "admin2")
    await _promote_to_admin(db_session, admin_id)

    update_response = await client.put(
        f"/products/{product_id}", json={"price": 42.0}, headers=_auth(admin_token)
    )
    assert update_response.status_code == 204

    delete_response = await client.delete(
        f"/products/{product_id}", headers=_auth(admin_token)
    )
    assert delete_response.status_code == 204


async def test_admin_can_list_product_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "owner4")
    await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "admin3")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get("/products/audit", headers=_auth(admin_token))

    assert response.status_code == 200
    # db_session изолирует каждый тест отдельной транзакцией с откатом
    # (см. conftest.py), поэтому в этой БД ровно одна audit-запись.
    assert len(response.json()) == 1

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
    client: AsyncClient,
    token: str,
    name: str = "Ноутбук",
    price: float = 1000.0,
    category: str = "Электроника",
) -> int:
    response = await client.post(
        "/products/",
        json={
            "name": name,
            "category": category,
            "price": price,
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


async def test_new_product_is_active_by_default(client: AsyncClient) -> None:
    _, owner_token = await _register_and_login(client, "defactive1")

    response = await client.post(
        "/products/",
        json={
            "name": "Ноутбук",
            "category": "Электроника",
            "price": 1000.0,
            "description": "Тестовый товар",
        },
        headers=_auth(owner_token),
    )

    assert response.status_code == 201
    assert response.json()["is_active"] is True


async def test_full_product_lifecycle_reflects_in_get_and_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "lifecycle1")

    product_id = await _create_product_via_http(client, owner_token, name="Ноутбук")

    get_response = await client.get(f"/products/{product_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Ноутбук"
    assert await _audit_actions(client, owner_token, product_id) == ["created"]

    update_response = await client.patch(
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

    # Явно фиксируем, что до удаления у владельца был полный доступ к
    # audit-логу — иначе тест ниже мог бы "случайно" пройти, если бы
    # доступ был закрыт по какой-то другой причине, не связанной с удалением.
    assert await _audit_actions(client, owner_token, product_id) == ["created"]

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
        f"/products/{999_999}/audit", headers=_auth(user_token)
    )
    admin_response = await client.get(
        f"/products/{999_999}/audit", headers=_auth(admin_token)
    )

    assert user_response.status_code == 404
    assert admin_response.status_code == 404


async def test_put_on_product_returns_405(client: AsyncClient) -> None:
    _, owner_token = await _register_and_login(client, "putgone1")
    product_id = await _create_product_via_http(client, owner_token)

    response = await client.put(
        f"/products/{product_id}", json={"price": 1.0}, headers=_auth(owner_token)
    )

    assert response.status_code == 405


async def test_patch_with_partial_body_leaves_omitted_fields_untouched(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "patchpart1")
    product_id = await _create_product_via_http(client, owner_token)

    update_response = await client.patch(
        f"/products/{product_id}", json={"price": 1500.0}, headers=_auth(owner_token)
    )
    assert update_response.status_code == 204

    get_response = await client.get(f"/products/{product_id}")
    body = get_response.json()
    assert body["price"] == 1500.0
    assert body["name"] == "Ноутбук"
    assert body["description"] == "Тестовый товар"


async def test_patch_updates_only_the_description_when_thats_all_thats_sent(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "patchdesc1")
    product_id = await _create_product_via_http(client, owner_token)

    update_response = await client.patch(
        f"/products/{product_id}",
        json={"description": "Обновлённое описание"},
        headers=_auth(owner_token),
    )
    assert update_response.status_code == 204

    get_response = await client.get(f"/products/{product_id}")
    body = get_response.json()
    assert body["description"] == "Обновлённое описание"
    assert body["price"] == 1000.0
    assert body["name"] == "Ноутбук"


async def test_non_owner_without_admin_cannot_update_a_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "owner1")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "intruder1")

    response = await client.patch(
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

    response = await client.get(
        "/products/audit",
        params={"page_index": 2, "page_size": 5},
        headers=_auth(token),
    )

    assert response.status_code == 403


async def test_admin_can_update_and_delete_a_foreign_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "owner3")
    product_id = await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "admin2")
    await _promote_to_admin(db_session, admin_id)

    update_response = await client.patch(
        f"/products/{product_id}", json={"price": 42.0}, headers=_auth(admin_token)
    )
    assert update_response.status_code == 204

    delete_response = await client.delete(
        f"/products/{product_id}", headers=_auth(admin_token)
    )
    assert delete_response.status_code == 204


async def test_admin_can_still_update_a_deactivated_owners_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # #19 скрывает GET /products/{id} деактивированного владельца от
    # не-admin, но не должен затрагивать мутации — они по-прежнему решают
    # доступ через _ensure_owner_or_admin, а не через фильтр видимости.
    admin_id, admin_token = await _register_and_login(client, "admin5")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "owner7")
    product_id = await _create_product_via_http(client, owner_token)

    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    response = await client.patch(
        f"/products/{product_id}", json={"price": 1234.0}, headers=_auth(admin_token)
    )

    assert response.status_code == 204


async def test_admin_can_still_delete_a_deactivated_owners_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "admin6")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "owner8")
    product_id = await _create_product_via_http(client, owner_token)

    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    response = await client.delete(
        f"/products/{product_id}", headers=_auth(admin_token)
    )

    assert response.status_code == 204


async def test_admin_can_still_read_audit_of_a_deactivated_owners_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "admin7")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "owner9")
    product_id = await _create_product_via_http(client, owner_token)

    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    response = await client.get(
        f"/products/{product_id}/audit", headers=_auth(admin_token)
    )

    assert response.status_code == 200
    assert [entry["action"] for entry in response.json()] == ["created"]


async def test_owner_can_deactivate_and_reactivate_their_own_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "toggle1")
    product_id = await _create_product_via_http(client, owner_token)

    deactivate_response = await client.patch(
        f"/products/{product_id}/deactivate", headers=_auth(owner_token)
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = await client.patch(
        f"/products/{product_id}/activate", headers=_auth(owner_token)
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


async def test_admin_can_deactivate_a_foreign_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "toggle2")
    product_id = await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "tadmin1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.patch(
        f"/products/{product_id}/deactivate", headers=_auth(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_non_owner_without_admin_cannot_deactivate_a_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "toggle3")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "tintr1")

    response = await client.patch(
        f"/products/{product_id}/deactivate", headers=_auth(intruder_token)
    )

    assert response.status_code == 403


async def test_non_owner_without_admin_cannot_activate_a_foreign_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "toggle4")
    product_id = await _create_product_via_http(client, owner_token)

    _, intruder_token = await _register_and_login(client, "tintr2")

    response = await client.patch(
        f"/products/{product_id}/activate", headers=_auth(intruder_token)
    )

    assert response.status_code == 403


async def test_deactivate_a_nonexistent_product_returns_404(
    client: AsyncClient,
) -> None:
    _, token = await _register_and_login(client, "toggle5")

    response = await client.patch(
        f"/products/{999_999}/deactivate", headers=_auth(token)
    )

    assert response.status_code == 404


async def test_activate_a_nonexistent_product_returns_404(
    client: AsyncClient,
) -> None:
    _, token = await _register_and_login(client, "toggle6")

    response = await client.patch(f"/products/{999_999}/activate", headers=_auth(token))

    assert response.status_code == 404


async def test_repeated_deactivate_call_is_idempotent_in_the_audit_log(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "toggle7")
    product_id = await _create_product_via_http(client, owner_token)

    first = await client.patch(
        f"/products/{product_id}/deactivate", headers=_auth(owner_token)
    )
    second = await client.patch(
        f"/products/{product_id}/deactivate", headers=_auth(owner_token)
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert await _audit_actions(client, owner_token, product_id) == [
        "created",
        "deactivated",
    ]


async def test_deactivate_and_reactivate_appear_in_audit_log_in_order(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "toggle8")
    product_id = await _create_product_via_http(client, owner_token)

    await client.patch(
        f"/products/{product_id}", json={"price": 1500.0}, headers=_auth(owner_token)
    )
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))
    await client.patch(f"/products/{product_id}/activate", headers=_auth(owner_token))

    assert await _audit_actions(client, owner_token, product_id) == [
        "created",
        "updated",
        "deactivated",
        "activated",
    ]


async def test_patch_cannot_change_is_active(client: AsyncClient) -> None:
    _, owner_token = await _register_and_login(client, "toggle9")
    product_id = await _create_product_via_http(client, owner_token)

    update_response = await client.patch(
        f"/products/{product_id}",
        json={"price": 1500.0, "is_active": False},
        headers=_auth(owner_token),
    )
    assert update_response.status_code == 204

    get_response = await client.get(f"/products/{product_id}")
    assert get_response.json()["is_active"] is True
    assert await _audit_actions(client, owner_token, product_id) == [
        "created",
        "updated",
    ]


async def test_get_deactivated_product_returns_404_for_anonymous_viewer(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib1")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.get(f"/products/{product_id}")

    assert response.status_code == 404


async def test_get_deactivated_product_returns_404_for_a_non_owner(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib2")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    _, other_token = await _register_and_login(client, "visib2b")
    response = await client.get(f"/products/{product_id}", headers=_auth(other_token))

    assert response.status_code == 404


async def test_get_deactivated_product_returns_200_for_its_owner(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib3")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.get(f"/products/{product_id}", headers=_auth(owner_token))

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_get_deactivated_product_returns_200_for_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "visib4")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    admin_id, admin_token = await _register_and_login(client, "visib4adm")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(f"/products/{product_id}", headers=_auth(admin_token))

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_owner_can_still_update_their_own_deactivated_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib5")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.patch(
        f"/products/{product_id}", json={"price": 42.0}, headers=_auth(owner_token)
    )

    assert response.status_code == 204


async def test_owner_can_still_delete_their_own_deactivated_product(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib6")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.delete(
        f"/products/{product_id}", headers=_auth(owner_token)
    )

    assert response.status_code == 204


async def test_products_list_hides_a_deactivated_product_even_from_its_owner(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "visib7")
    product_id = await _create_product_via_http(client, owner_token, name="Скрытый")
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.get("/products/", headers=_auth(owner_token))

    assert response.status_code == 200
    assert product_id not in [item["id"] for item in response.json()["items"]]


async def test_products_list_shows_a_deactivated_product_to_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "visib8")
    product_id = await _create_product_via_http(client, owner_token, name="Скрытый")
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    admin_id, admin_token = await _register_and_login(client, "visib8adm")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get("/products/", headers=_auth(admin_token))

    assert response.status_code == 200
    assert product_id in [item["id"] for item in response.json()["items"]]


async def test_admin_can_list_product_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "owner4")
    await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "admin3")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get("/products/audit", headers=_auth(admin_token))

    assert response.status_code == 200
    body = response.json()
    # db_session изолирует каждый тест отдельной транзакцией с откатом
    # (см. conftest.py), поэтому в этой БД ровно одна audit-запись.
    assert body["total"] == 1
    assert body["page_index"] == 1
    assert body["page_size"] == 10
    assert body["total_pages"] == 1
    assert [entry["action"] for entry in body["items"]] == ["created"]


async def test_admin_can_paginate_product_audit_across_pages(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "audpgowner")
    product_ids = [
        await _create_product_via_http(client, owner_token, name=f"Товар {i}")
        for i in range(3)
    ]

    admin_id, admin_token = await _register_and_login(client, "audpgadmin")
    await _promote_to_admin(db_session, admin_id)

    first_page = await client.get(
        "/products/audit",
        params={"page_index": 1, "page_size": 2},
        headers=_auth(admin_token),
    )
    second_page = await client.get(
        "/products/audit",
        params={"page_index": 2, "page_size": 2},
        headers=_auth(admin_token),
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first_body, second_body = first_page.json(), second_page.json()
    assert len(first_body["items"]) == 2
    assert len(second_body["items"]) == 1
    assert first_body["total"] == 3
    assert first_body["total_pages"] == 2
    first_ids = {item["id"] for item in first_body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)
    # Новые записи первыми: товар, созданный последним, идёт первым в items.
    product_ids_in_order = [
        item["product_id"] for item in first_body["items"] + second_body["items"]
    ]
    assert product_ids_in_order == list(reversed(product_ids))


async def test_product_audit_page_beyond_range_returns_empty_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "audrgowner")
    await _create_product_via_http(client, owner_token)

    admin_id, admin_token = await _register_and_login(client, "audrgadmin")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit",
        params={"page_index": 999, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 1
    assert body["total_pages"] == 1


async def test_product_audit_page_rejects_page_index_below_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "audbadidx1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit", params={"page_index": 0}, headers=_auth(admin_token)
    )

    assert response.status_code == 422


async def test_product_audit_page_rejects_page_size_below_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "audbadsiz1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit", params={"page_size": 0}, headers=_auth(admin_token)
    )

    assert response.status_code == 422


async def test_product_audit_sort_by_created_at_ascending_orders_oldest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "srtcaown1")
    admin_id, admin_token = await _register_and_login(client, "srtcaadm1")
    await _promote_to_admin(db_session, admin_id)
    first_id = await _create_product_via_http(client, owner_token, name="Товар А")
    second_id = await _create_product_via_http(client, owner_token, name="Товар Б")

    response = await client.get(
        "/products/audit",
        params={"sort_by": "created_at", "sort_desc": False, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert response.status_code == 200
    assert [item["product_id"] for item in response.json()["items"]] == [
        first_id,
        second_id,
    ]


async def test_product_audit_sort_by_action_orders_by_the_action_column(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # action — нативный Postgres ENUM, сортируется по порядковому номеру
    # объявления значения в типе (CREATED, UPDATED, DELETED, ACTIVATED,
    # DEACTIVATED, см. alembic/versions), а не по алфавиту строки: отсюда
    # created < updated < activated < deactivated, а не алфавитный порядок.
    _, owner_token = await _register_and_login(client, "srtacown1")
    product_id = await _create_product_via_http(client, owner_token)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))
    await client.patch(f"/products/{product_id}/activate", headers=_auth(owner_token))
    await client.patch(
        f"/products/{product_id}", json={"price": 1234.0}, headers=_auth(owner_token)
    )
    admin_id, admin_token = await _register_and_login(client, "srtacadm1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit",
        params={"sort_by": "action", "sort_desc": False, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert response.status_code == 200
    assert [item["action"] for item in response.json()["items"]] == [
        "created",
        "updated",
        "activated",
        "deactivated",
    ]


async def test_product_audit_sort_by_actor_user_id_orders_by_actor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Регистрируем lo раньше hi (lo_id < hi_id), но hi создаёт товар первым —
    # actor_user_id и created_at идут в противоположных порядках, так что
    # тест ловит и ситуацию, когда sort_by молча игнорируется в пользу
    # дефолтной сортировки по created_at.
    lo_id, lo_token = await _register_and_login(client, "srtaulo1")
    hi_id, hi_token = await _register_and_login(client, "srtauhi1")
    assert lo_id < hi_id
    await _create_product_via_http(client, hi_token, name="Товар Hi")
    await _create_product_via_http(client, lo_token, name="Товар Lo")
    admin_id, admin_token = await _register_and_login(client, "srtauadm1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit",
        params={"sort_by": "actor_user_id", "sort_desc": False, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert response.status_code == 200
    assert [item["actor_user_id"] for item in response.json()["items"]] == [
        lo_id,
        hi_id,
    ]


async def test_product_audit_sort_by_product_id_orders_by_product_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "srtpiown1")
    admin_id, admin_token = await _register_and_login(client, "srtpiadm1")
    await _promote_to_admin(db_session, admin_id)
    first_id = await _create_product_via_http(client, owner_token, name="Товар А")
    second_id = await _create_product_via_http(client, owner_token, name="Товар Б")

    response = await client.get(
        "/products/audit",
        params={"sort_by": "product_id", "sort_desc": True, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert response.status_code == 200
    assert [item["product_id"] for item in response.json()["items"]] == [
        second_id,
        first_id,
    ]


async def test_product_audit_sort_desc_false_reverses_the_default_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "srtdsown1")
    admin_id, admin_token = await _register_and_login(client, "srtdsadm1")
    await _promote_to_admin(db_session, admin_id)
    first_id = await _create_product_via_http(client, owner_token, name="Товар А")
    second_id = await _create_product_via_http(client, owner_token, name="Товар Б")

    descending = await client.get(
        "/products/audit", params={"page_size": 10}, headers=_auth(admin_token)
    )
    ascending = await client.get(
        "/products/audit",
        params={"sort_desc": False, "page_size": 10},
        headers=_auth(admin_token),
    )

    assert descending.status_code == 200
    assert ascending.status_code == 200
    assert [item["product_id"] for item in descending.json()["items"]] == [
        second_id,
        first_id,
    ]
    assert [item["product_id"] for item in ascending.json()["items"]] == [
        first_id,
        second_id,
    ]


async def test_product_audit_rejects_an_invalid_sort_by_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "srtbadfl1")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        "/products/audit",
        params={"sort_by": "description"},
        headers=_auth(admin_token),
    )

    assert response.status_code == 422


async def test_product_audit_pagination_totals_stay_correct_with_a_custom_sort(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # AC #36: page_index/page_size/total/total_pages должны продолжать
    # корректно работать в комбинации с любым sort_by/sort_desc, а не только
    # с дефолтной сортировкой по created_at.
    _, owner_token = await _register_and_login(client, "srtpgown1")
    admin_id, admin_token = await _register_and_login(client, "srtpgadm1")
    await _promote_to_admin(db_session, admin_id)
    first_id = await _create_product_via_http(client, owner_token, name="Товар А")
    second_id = await _create_product_via_http(client, owner_token, name="Товар Б")
    third_id = await _create_product_via_http(client, owner_token, name="Товар В")

    first_page = await client.get(
        "/products/audit",
        params={
            "sort_by": "product_id",
            "sort_desc": False,
            "page_index": 1,
            "page_size": 2,
        },
        headers=_auth(admin_token),
    )
    second_page = await client.get(
        "/products/audit",
        params={
            "sort_by": "product_id",
            "sort_desc": False,
            "page_index": 2,
            "page_size": 2,
        },
        headers=_auth(admin_token),
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first_body, second_body = first_page.json(), second_page.json()
    assert first_body["total"] == 3
    assert first_body["total_pages"] == 2
    assert second_body["total"] == 3
    assert second_body["total_pages"] == 2
    assert [item["product_id"] for item in first_body["items"]] == [
        first_id,
        second_id,
    ]
    assert [item["product_id"] for item in second_body["items"]] == [third_id]

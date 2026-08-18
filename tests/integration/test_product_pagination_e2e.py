import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_product_e2e import (
    _auth,
    _create_product_via_http,
    _promote_to_admin,
    _register_and_login,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_products_without_a_token_returns_the_envelope_shape(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "pagowner1")
    await _create_product_via_http(client, owner_token, name="Ноутбук")

    response = await client.get("/products/")

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert set(body["page_info"]) == {
        "next_cursor",
        "prev_cursor",
        "has_more",
        "has_prev",
    }


async def test_get_products_orders_newest_first(client: AsyncClient) -> None:
    _, owner_token = await _register_and_login(client, "pagowner2")
    await _create_product_via_http(client, owner_token, name="Первый")
    await _create_product_via_http(client, owner_token, name="Второй")
    await _create_product_via_http(client, owner_token, name="Третий")

    response = await client.get("/products/")

    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Третий", "Второй", "Первый"]


async def test_get_products_respects_the_limit_query_param(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "pagowner3")
    await _create_product_via_http(client, owner_token, name="Первый")
    await _create_product_via_http(client, owner_token, name="Второй")
    await _create_product_via_http(client, owner_token, name="Третий")

    response = await client.get("/products/", params={"limit": 1})

    body = response.json()
    assert len(body["items"]) == 1
    assert body["page_info"]["has_more"] is True


async def test_get_products_rejects_a_limit_above_the_maximum(
    client: AsyncClient,
) -> None:
    response = await client.get("/products/", params={"limit": 101})

    assert response.status_code == 422


async def test_get_products_rejects_a_limit_below_one(client: AsyncClient) -> None:
    response = await client.get("/products/", params={"limit": 0})

    assert response.status_code == 422


async def test_get_products_after_cursor_returns_the_next_page(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "pagowner4")
    await _create_product_via_http(client, owner_token, name="Первый")
    await _create_product_via_http(client, owner_token, name="Второй")
    await _create_product_via_http(client, owner_token, name="Третий")

    first_page = (await client.get("/products/", params={"limit": 2})).json()
    assert [item["name"] for item in first_page["items"]] == ["Третий", "Второй"]

    second_page = (
        await client.get(
            "/products/",
            params={"limit": 2, "after": first_page["page_info"]["next_cursor"]},
        )
    ).json()

    assert [item["name"] for item in second_page["items"]] == ["Первый"]
    assert second_page["page_info"]["has_more"] is False
    assert second_page["page_info"]["next_cursor"] is None
    assert second_page["page_info"]["has_prev"] is True
    assert second_page["page_info"]["prev_cursor"] is not None


async def test_get_products_before_cursor_returns_back_to_the_previous_page(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "pagowner9")
    await _create_product_via_http(client, owner_token, name="Первый")
    await _create_product_via_http(client, owner_token, name="Второй")
    await _create_product_via_http(client, owner_token, name="Третий")

    first_page = (await client.get("/products/", params={"limit": 2})).json()
    second_page = (
        await client.get(
            "/products/",
            params={"limit": 2, "after": first_page["page_info"]["next_cursor"]},
        )
    ).json()

    back_to_first_page = (
        await client.get(
            "/products/",
            params={"limit": 2, "before": second_page["page_info"]["prev_cursor"]},
        )
    ).json()

    assert [item["name"] for item in back_to_first_page["items"]] == [
        "Третий",
        "Второй",
    ]
    assert back_to_first_page["page_info"]["has_prev"] is False
    assert back_to_first_page["page_info"]["prev_cursor"] is None


async def test_get_products_first_page_has_no_prev_cursor(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "pagowner5")
    await _create_product_via_http(client, owner_token)

    response = await client.get("/products/")

    body = response.json()
    assert body["page_info"]["has_prev"] is False
    assert body["page_info"]["prev_cursor"] is None


async def test_get_products_with_no_products_returns_an_empty_envelope(
    client: AsyncClient,
) -> None:
    response = await client.get("/products/")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page_info": {
            "next_cursor": None,
            "prev_cursor": None,
            "has_more": False,
            "has_prev": False,
        },
    }


async def test_get_products_rejects_both_after_and_before_at_once(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/products/", params={"after": "whatever", "before": "whatever"}
    )

    assert response.status_code == 400


async def test_get_products_rejects_a_malformed_cursor(client: AsyncClient) -> None:
    response = await client.get("/products/", params={"after": "not-valid-base64!!!"})

    assert response.status_code == 400


async def test_get_products_hides_products_of_a_deactivated_owner_for_anonymous_callers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "pagadmin1")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "pagowner6")
    await _create_product_via_http(client, owner_token, name="Скрытый")

    deactivate_response = await client.patch(
        f"/users/{owner_id}/deactivate", headers=_auth(admin_token)
    )
    assert deactivate_response.status_code == 200

    response = await client.get("/products/")

    assert response.json()["items"] == []


async def test_get_products_hides_products_of_a_deactivated_owner_for_regular_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "pagadmin2")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "pagowner7")
    await _create_product_via_http(client, owner_token, name="Скрытый")

    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    _, other_token = await _register_and_login(client, "pagviewer1")
    response = await client.get("/products/", headers=_auth(other_token))

    assert response.json()["items"] == []


async def test_get_products_shows_products_of_a_deactivated_owner_to_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "pagadmin3")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "pagowner8")
    await _create_product_via_http(client, owner_token, name="Скрытый")

    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    response = await client.get("/products/", headers=_auth(admin_token))

    assert [item["name"] for item in response.json()["items"]] == ["Скрытый"]


async def test_get_products_with_an_invalid_token_returns_401_not_anonymous(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/products/", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401


async def test_get_products_with_a_deactivated_callers_token_returns_403_not_anonymous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "pagadmin4")
    await _promote_to_admin(db_session, admin_id)

    caller_id, caller_token = await _register_and_login(client, "pagcaller1")
    await client.patch(f"/users/{caller_id}/deactivate", headers=_auth(admin_token))

    response = await client.get("/products/", headers=_auth(caller_token))

    assert response.status_code == 403

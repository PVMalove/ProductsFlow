import uuid
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.owner_read_model import (
    get_owner_read_model,
    upsert_owner_read_model,
)
from tests.integration.fake_identity_gateway import FakeIdentityGateway

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PRODUCT_PAYLOAD = {
    "name": "Название товара",
    "description": "Описание",
    "price": 9.99,
    "category": "Категория",
}
_UNKNOWN_PRODUCT_ID = uuid.uuid4()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_owner(identity_gateway: FakeIdentityGateway) -> tuple[str, uuid.UUID]:
    owner_id = uuid.uuid4()
    token = f"token-{owner_id}"
    identity_gateway.register(token, user_id=owner_id)
    return token, owner_id


def _register_admin(identity_gateway: FakeIdentityGateway) -> tuple[str, uuid.UUID]:
    admin_id = uuid.uuid4()
    token = f"token-{admin_id}"
    identity_gateway.register(token, user_id=admin_id, role="admin")
    return token, admin_id


async def _create_product(
    client: httpx.AsyncClient, token: str, **overrides: object
) -> dict[str, object]:
    payload = {**_PRODUCT_PAYLOAD, **overrides}
    response = await client.post("/api/v1/products", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    envelope: dict[str, object] = response.json()
    assert envelope["meta"] == {}
    return cast(dict[str, object], envelope["data"])


# --- Создание (story 1) ---------------------------------------------------


async def test_create_product_requires_authentication(
    catalog_client: httpx.AsyncClient,
) -> None:
    response = await catalog_client.post("/api/v1/products", json=_PRODUCT_PAYLOAD)
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Требуется авторизация"}
    }


async def test_create_product_persists_it_under_the_caller(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, owner_id = _register_owner(identity_gateway)

    body = await _create_product(catalog_client, token)

    assert body["name"] == _PRODUCT_PAYLOAD["name"]
    assert body["user_id"] == str(owner_id)
    assert body["is_active"] is True


async def test_create_product_returns_the_bff_success_envelope(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    """ADR 0031: `data`/`meta` обязательны, `meta` пуст для create."""
    token, _ = _register_owner(identity_gateway)

    response = await catalog_client.post(
        "/api/v1/products", json=_PRODUCT_PAYLOAD, headers=_auth(token)
    )

    assert response.status_code == 201
    assert set(response.json().keys()) == {"data", "meta"}
    assert response.json()["meta"] == {}


async def test_create_product_seeds_owner_read_model_on_cold_miss(
    catalog_client: httpx.AsyncClient,
    identity_gateway: FakeIdentityGateway,
    db_session: AsyncSession,
) -> None:
    """Story 15 (ADR 0012/0019): холодный промах закрывается на создании,
    строка с сентинелом 0 появляется до того, как её кто-то спросит."""
    token, owner_id = _register_owner(identity_gateway)

    await _create_product(catalog_client, token)

    row = await get_owner_read_model(db_session, owner_id)
    assert row is not None
    assert row.is_active is True
    assert row.last_applied_outbox_id == 0


async def test_create_product_rejects_invalid_payload(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)

    response = await catalog_client.post(
        "/api/v1/products",
        json={**_PRODUCT_PAYLOAD, "name": "аб"},
        headers=_auth(token),
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_name",
            "message": "Название должно быть от 3 до 100 символов",
        }
    }


async def test_create_product_rejects_a_malformed_request_body(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    """Framework-level Pydantic validation (не доменная) — тоже структурная
    error-shape, но с каноническим VALIDATION_ERROR (ADR 0031)."""
    token, _ = _register_owner(identity_gateway)

    response = await catalog_client.post(
        "/api/v1/products",
        json={**_PRODUCT_PAYLOAD, "price": "not-a-number"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "VALIDATION_ERROR", "message": "Некорректные данные запроса"}
    }


async def test_create_product_fails_closed_when_identity_is_unavailable_on_cold_miss(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    identity_gateway.unavailable = True

    response = await catalog_client.post(
        "/api/v1/products", json=_PRODUCT_PAYLOAD, headers=_auth(token)
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "IDENTITY_UNAVAILABLE",
            "message": "identity-service недоступен",
        }
    }


# --- Прямой доступ по id (stories 6, 9, 12) -------------------------------


async def test_get_unknown_product_returns_404(
    catalog_client: httpx.AsyncClient,
) -> None:
    response = await catalog_client.get(f"/api/v1/products/{_UNKNOWN_PRODUCT_ID}")
    assert response.status_code == 404


async def test_get_active_product_is_visible_to_anonymous_viewer(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)

    response = await catalog_client.get(f"/api/v1/products/{product['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == product["id"]


async def test_get_deactivated_product_is_hidden_from_anonymous_viewer(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )

    response = await catalog_client.get(f"/api/v1/products/{product['id']}")

    assert response.status_code == 404


async def test_get_deactivated_product_is_visible_to_its_owner(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}", headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_get_deactivated_product_is_visible_to_an_admin(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    admin_token, _ = _register_admin(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(owner_token)
    )

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}", headers=_auth(admin_token)
    )

    assert response.status_code == 200


async def test_get_product_is_hidden_when_its_owner_is_deactivated(
    catalog_client: httpx.AsyncClient,
    identity_gateway: FakeIdentityGateway,
    db_session: AsyncSession,
) -> None:
    owner_token, owner_id = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    # Владелец деактивирован в identity — read-модель отражает это тем же
    # upsert-механизмом, каким это в production сделает консьюмер событий
    # (issue #151, вне скоупа этого issue) — здесь сеется напрямую (ADR 0018).
    await upsert_owner_read_model(
        db_session,
        user_id=owner_id,
        role="user",
        is_active=False,
        last_applied_outbox_id=1,
    )

    other_token, _ = _register_owner(identity_gateway)

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}", headers=_auth(other_token)
    )

    assert response.status_code == 404


# --- Списки (stories 9, 10) ------------------------------------------------


async def test_list_hides_deactivated_products_from_anonymous_viewer(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    visible = await _create_product(catalog_client, token, name="Видимый товар")
    hidden = await _create_product(catalog_client, token, name="Скрытый товар")
    await catalog_client.patch(
        f"/api/v1/products/{hidden['id']}/deactivate", headers=_auth(token)
    )

    response = await catalog_client.get("/api/v1/products")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert visible["id"] in ids
    assert hidden["id"] not in ids


# --- Обновление (story 2) ---------------------------------------------------


async def test_update_product_changes_only_provided_fields(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)

    response = await catalog_client.patch(
        f"/api/v1/products/{product['id']}",
        json={"price": 42.0},
        headers=_auth(token),
    )

    assert response.status_code == 204
    fetched = await catalog_client.get(
        f"/api/v1/products/{product['id']}", headers=_auth(token)
    )
    body = fetched.json()
    assert body["price"] == 42.0
    assert body["name"] == _PRODUCT_PAYLOAD["name"]


async def test_update_product_by_a_non_owner_non_admin_is_forbidden(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.patch(
        f"/api/v1/products/{product['id']}",
        json={"price": 1.0},
        headers=_auth(other_token),
    )

    assert response.status_code == 403


async def test_update_product_by_an_admin_who_is_not_the_owner_is_allowed(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    admin_token, _ = _register_admin(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.patch(
        f"/api/v1/products/{product['id']}",
        json={"price": 1.0},
        headers=_auth(admin_token),
    )

    assert response.status_code == 204


async def test_update_product_fails_closed_when_identity_is_unavailable(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    identity_gateway.unavailable = True

    response = await catalog_client.patch(
        f"/api/v1/products/{product['id']}",
        json={"price": 1.0},
        headers=_auth(other_token),
    )

    assert response.status_code == 503


# --- Активация/деактивация (stories 3, 4) ----------------------------------


async def test_deactivate_then_activate_product_round_trips(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)

    deactivated = await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    activated = await catalog_client.patch(
        f"/api/v1/products/{product['id']}/activate", headers=_auth(token)
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


async def test_deactivate_an_already_deactivated_product_is_a_conflict(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )

    response = await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )

    assert response.status_code == 409


# --- Удаление (story 5) -----------------------------------------------------


async def test_delete_product_by_owner_removes_it(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)

    response = await catalog_client.delete(
        f"/api/v1/products/{product['id']}", headers=_auth(token)
    )
    assert response.status_code == 204

    fetched = await catalog_client.get(
        f"/api/v1/products/{product['id']}", headers=_auth(token)
    )
    assert fetched.status_code == 404


async def test_delete_product_by_a_non_owner_non_admin_is_forbidden(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.delete(
        f"/api/v1/products/{product['id']}", headers=_auth(other_token)
    )

    assert response.status_code == 403


# --- Audit-лог (story 13) ---------------------------------------------------


async def test_audit_log_is_visible_to_the_owner(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, token)
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate", headers=_auth(token)
    )

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}/audit", headers=_auth(token)
    )

    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert "created" in actions
    assert "deactivated" in actions


async def test_audit_log_is_forbidden_for_a_non_owner_non_admin(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}/audit", headers=_auth(other_token)
    )

    assert response.status_code == 403


async def test_audit_log_survives_product_deletion_for_an_admin(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    admin_token, _ = _register_admin(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    await catalog_client.delete(
        f"/api/v1/products/{product['id']}", headers=_auth(owner_token)
    )

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}/audit", headers=_auth(admin_token)
    )

    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert "deleted" in actions


async def test_audit_log_for_a_deleted_product_is_forbidden_for_a_non_admin(
    catalog_client: httpx.AsyncClient, identity_gateway: FakeIdentityGateway
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    await catalog_client.delete(
        f"/api/v1/products/{product['id']}", headers=_auth(owner_token)
    )

    response = await catalog_client.get(
        f"/api/v1/products/{product['id']}/audit", headers=_auth(other_token)
    )

    assert response.status_code == 403

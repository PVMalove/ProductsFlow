import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from domain.product_id import ProductId
from infrastructure.db.product_repository import ProductRepository
from tests.integration.conftest import FakeImageStorage

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PRODUCT_PAYLOAD = {
    "name": "Название товара",
    "description": "Описание",
    "price": 9.99,
    "category": "Категория",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_owner(identity_gateway: object) -> tuple[str, uuid.UUID]:
    owner_id = uuid.uuid4()
    token = f"token-{owner_id}"
    identity_gateway.register(token, user_id=owner_id)  # type: ignore[attr-defined]
    return token, owner_id


def _register_user(identity_gateway: object) -> tuple[str, uuid.UUID]:
    return _register_owner(identity_gateway)


def _register_admin(identity_gateway: object) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    token = f"token-{user_id}"
    identity_gateway.register(  # type: ignore[attr-defined]
        token, user_id=user_id, role="admin"
    )
    return token, user_id


async def _create_product(client: httpx.AsyncClient, token: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/products", json=_PRODUCT_PAYLOAD, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()["data"]
    return data


def _file(
    content_type: str = "image/jpeg", body: bytes = b"image-bytes"
) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("image.jpg", body, content_type)}


async def _upload(
    client: httpx.AsyncClient,
    product_id: object,
    token: str,
    *,
    content_type: str = "image/jpeg",
    body: bytes = b"image-bytes",
) -> httpx.Response:
    return await client.post(
        f"/api/v1/products/{product_id}/image",
        headers=_auth(token),
        files=_file(content_type=content_type, body=body),
    )


async def test_owner_can_upload_and_read_product_image(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
    image_storage: FakeImageStorage,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.post(
        f"/api/v1/products/{product['id']}/image",
        headers=_auth(owner_token),
        files=_file(content_type="image/png"),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "/products/" in body["image_url"]
    assert "X-Amz-Signature=" in body["image_url"]
    assert any(
        key == f"products/{product['id']}/image"
        for _bucket, key in image_storage.objects
    )

    read_response = await catalog_client.get(f"/api/v1/products/{product['id']}/image")
    assert read_response.status_code == 200
    assert (
        read_response.json()["image_url"].split("?")[0]
        == body["image_url"].split("?")[0]
    )


async def test_visible_product_without_image_has_distinct_not_found_message(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    response = await catalog_client.get(f"/api/v1/products/{product['id']}/image")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "У товара нет картинки!"
    unknown = await catalog_client.get(f"/api/v1/products/{uuid.uuid4()}/image")
    assert unknown.json()["error"]["message"] == "Товар не найден"


async def test_image_visibility_follows_product_visibility(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    admin_token, _ = _register_admin(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    assert (
        await _upload(catalog_client, product["id"], owner_token)
    ).status_code == 201
    await catalog_client.patch(
        f"/api/v1/products/{product['id']}/deactivate",
        headers=_auth(owner_token),
    )

    anonymous = await catalog_client.get(f"/api/v1/products/{product['id']}/image")
    owner = await catalog_client.get(
        f"/api/v1/products/{product['id']}/image",
        headers=_auth(owner_token),
    )

    assert anonymous.status_code == 404
    assert anonymous.json()["error"]["message"] == "Товар не найден"
    assert owner.status_code == 200
    admin = await catalog_client.get(
        f"/api/v1/products/{product['id']}/image",
        headers=_auth(admin_token),
    )
    assert admin.status_code == 200


async def test_non_owner_cannot_mutate_image_and_invalid_uploads_are_rejected(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_user(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    forbidden = await _upload(catalog_client, product["id"], other_token)
    unsupported = await _upload(
        catalog_client,
        product["id"],
        owner_token,
        content_type="application/pdf",
    )
    too_large = await _upload(
        catalog_client,
        product["id"],
        owner_token,
        body=b"x" * (5 * 1024 * 1024 + 1),
    )

    assert forbidden.status_code == 403
    assert unsupported.status_code == 415
    assert too_large.status_code == 413


async def test_delete_without_image_is_distinct_and_non_owner_is_forbidden(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    other_token, _ = _register_user(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    missing = await catalog_client.delete(
        f"/api/v1/products/{product['id']}/image",
        headers=_auth(owner_token),
    )
    uploaded = await _upload(catalog_client, product["id"], owner_token)
    assert uploaded.status_code == 201
    forbidden = await catalog_client.delete(
        f"/api/v1/products/{product['id']}/image",
        headers=_auth(other_token),
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["message"] == "У товара нет картинки!"
    assert forbidden.status_code == 403


async def test_replace_delete_and_admin_access_are_supported(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
    image_storage: FakeImageStorage,
) -> None:
    owner_token, _owner_id = _register_owner(identity_gateway)
    admin_token, admin_id = _register_admin(identity_gateway)
    product = await _create_product(catalog_client, owner_token)

    first = await _upload(catalog_client, product["id"], owner_token)
    second = await _upload(
        catalog_client,
        product["id"],
        owner_token,
        content_type="image/webp",
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert (
        first.json()["image_url"].split("?")[0]
        == second.json()["image_url"].split("?")[0]
    )

    deleted = await catalog_client.delete(
        f"/api/v1/products/{product['id']}/image", headers=_auth(admin_token)
    )
    assert deleted.status_code == 204
    after_delete = await catalog_client.get(f"/api/v1/products/{product['id']}/image")
    assert after_delete.status_code == 404
    assert any(
        key == f"products/{product['id']}/image"
        for _bucket, key in image_storage.deleted
    )

    audit = await catalog_client.get(
        f"/api/v1/products/{product['id']}/audit", headers=_auth(owner_token)
    )
    audit_entries = audit.json()["data"]
    assert [entry["action"] for entry in audit_entries][:2] == [
        "image_deleted",
        "image_updated",
    ]
    assert audit_entries[0]["actor_user_id"] == str(admin_id)


async def test_seed_object_is_not_deleted(
    catalog_client: httpx.AsyncClient,
    identity_gateway: object,
    image_storage: FakeImageStorage,
    db_session: AsyncSession,
) -> None:
    owner_token, _ = _register_owner(identity_gateway)
    product = await _create_product(catalog_client, owner_token)
    raw_product_id = product["id"]
    assert isinstance(raw_product_id, str)
    product_id = uuid.UUID(raw_product_id)
    await ProductRepository(db_session).upsert_product_image(
        ProductId(product_id),
        s3_key="seed/placeholder.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        actor_user_id=uuid.uuid4(),
    )

    response = await catalog_client.delete(
        f"/api/v1/products/{product_id}/image", headers=_auth(owner_token)
    )

    assert response.status_code == 204
    assert image_storage.deleted == []

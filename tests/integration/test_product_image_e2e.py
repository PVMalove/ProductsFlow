import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SEED_PLACEHOLDER_KEY
from app.models import ProductAuditAction, ProductAuditLog, ProductImage
from app.settings import settings
from app.storage import get_storage
from tests.integration.test_product_e2e import (
    _auth,
    _create_product_via_http,
    _promote_to_admin,
    _register_and_login,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

IMAGE_PATH = "/api/v2/products/{product_id}/image"


async def _attach_image(
    session: AsyncSession,
    product_id: int,
    s3_key: str = "products/1/image.jpg",
    content_type: str = "image/jpeg",
    size_bytes: int = 123,
) -> ProductImage:
    image = ProductImage(
        product_id=product_id,
        s3_key=s3_key,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image


async def test_v2_image_route_does_not_exist_under_v1(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgv1owner")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)

    response = await client.get(f"/api/v1/products/{product_id}/image")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


async def test_get_product_image_returns_200_with_url_and_updated_at_for_anonymous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner1")
    product_id = await _create_product_via_http(client, owner_token)
    image = await _attach_image(
        db_session, product_id, s3_key=f"products/{product_id}/image.jpg"
    )

    response = await client.get(IMAGE_PATH.format(product_id=product_id))

    assert response.status_code == 200
    body = response.json()
    expected_url = get_storage().build_public_url(
        settings.minio_bucket_name_product,
        image.s3_key,
        int(image.updated_at.timestamp()),
    )
    assert body["image_url"] == expected_url


async def test_get_product_image_returns_200_for_a_regular_authenticated_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner9")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)

    _, viewer_token = await _register_and_login(client, "imgviewer9")
    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(viewer_token)
    )

    assert response.status_code == 200


async def test_get_product_image_404_message_matches_direct_get_for_nonexistent_product(
    client: AsyncClient,
) -> None:
    direct_response = await client.get("/products/999999")
    image_response = await client.get(IMAGE_PATH.format(product_id=999999))

    assert direct_response.status_code == 404
    assert image_response.status_code == 404
    assert image_response.json()["detail"] == direct_response.json()["detail"]


async def test_get_product_image_404_message_matches_direct_get_for_deactivated_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner2")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    direct_response = await client.get(f"/products/{product_id}")
    image_response = await client.get(IMAGE_PATH.format(product_id=product_id))

    assert direct_response.status_code == 404
    assert image_response.status_code == 404
    assert image_response.json()["detail"] == direct_response.json()["detail"]


async def test_get_product_image_404_for_non_owner_when_product_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner3")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    _, other_token = await _register_and_login(client, "imgother3")
    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(other_token)
    )

    assert response.status_code == 404


async def test_get_product_image_200_for_owner_when_product_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner4")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(owner_token)
    )

    assert response.status_code == 200


async def test_get_product_image_200_for_admin_when_product_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner5")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/products/{product_id}/deactivate", headers=_auth(owner_token))

    admin_id, admin_token = await _register_and_login(client, "imgadmin5")
    await _promote_to_admin(db_session, admin_id)

    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(admin_token)
    )

    assert response.status_code == 200


async def test_get_product_image_404_for_regular_viewer_when_owner_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "imgadmin6")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "imgowner6")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    _, other_token = await _register_and_login(client, "imgother6")
    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(other_token)
    )

    assert response.status_code == 404


async def test_get_product_image_200_for_admin_when_owner_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, admin_token = await _register_and_login(client, "imgadmin7")
    await _promote_to_admin(db_session, admin_id)

    owner_id, owner_token = await _register_and_login(client, "imgowner7")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    await client.patch(f"/users/{owner_id}/deactivate", headers=_auth(admin_token))

    response = await client.get(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(admin_token)
    )

    assert response.status_code == 200


async def test_get_product_image_returns_distinct_404_when_product_has_no_image(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "imgowner8")
    product_id = await _create_product_via_http(client, owner_token)

    not_found_response = await client.get("/products/999999")
    no_image_response = await client.get(IMAGE_PATH.format(product_id=product_id))

    assert no_image_response.status_code == 404
    assert no_image_response.json()["detail"] != not_found_response.json()["detail"]


def _file(content_type: str = "image/jpeg", body: bytes = b"fake-bytes") -> dict:
    return {"file": ("image.jpg", body, content_type)}


async def test_post_product_image_201_on_first_upload(
    client: AsyncClient, minio_ready: None
) -> None:
    _, owner_token = await _register_and_login(client, "postowner1")
    product_id = await _create_product_via_http(client, owner_token)

    response = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(),
    )

    assert response.status_code == 201
    body = response.json()
    assert "image_url" in body
    assert "updated_at" in body


async def test_post_product_image_200_on_replace_with_stable_key(
    client: AsyncClient, minio_ready: None
) -> None:
    _, owner_token = await _register_and_login(client, "postowner2")
    product_id = await _create_product_via_http(client, owner_token)
    first = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(),
    )
    assert first.status_code == 201
    first_url_base = first.json()["image_url"].split("?")[0]

    second = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(content_type="image/png"),
    )

    assert second.status_code == 200
    assert second.json()["image_url"].split("?")[0] == first_url_base


async def test_post_product_image_403_for_non_owner_non_admin(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "postowner3")
    product_id = await _create_product_via_http(client, owner_token)
    _, other_token = await _register_and_login(client, "postother3")

    response = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(other_token),
        files=_file(),
    )

    assert response.status_code == 403


async def test_post_product_image_415_for_disallowed_content_type(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "postowner4")
    product_id = await _create_product_via_http(client, owner_token)

    response = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(content_type="application/pdf"),
    )

    assert response.status_code == 415


async def test_post_product_image_does_not_delete_shared_seed_placeholder(
    client: AsyncClient, db_session: AsyncSession, minio_ready: None
) -> None:
    storage = get_storage()
    await storage.put_object(
        settings.minio_bucket_name_product,
        SEED_PLACEHOLDER_KEY,
        b"placeholder-bytes",
        "image/jpeg",
    )
    _, owner_token = await _register_and_login(client, "postowner6")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id, s3_key=SEED_PLACEHOLDER_KEY)
    other_product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, other_product_id, s3_key=SEED_PLACEHOLDER_KEY)

    response = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(),
    )

    assert response.status_code == 200
    async with storage.client() as s3_client:
        await s3_client.head_object(
            Bucket=settings.minio_bucket_name_product, Key=SEED_PLACEHOLDER_KEY
        )
    other_image_response = await client.get(
        IMAGE_PATH.format(product_id=other_product_id)
    )
    assert (
        other_image_response.json()["image_url"]
        .split("?")[0]
        .endswith(SEED_PLACEHOLDER_KEY)
    )


async def test_delete_product_image_404_when_no_image(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "delowner1")
    product_id = await _create_product_via_http(client, owner_token)
    no_image_get = await client.get(IMAGE_PATH.format(product_id=product_id))

    response = await client.delete(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(owner_token)
    )

    assert response.status_code == 404
    assert response.json()["detail"] == no_image_get.json()["detail"]


async def test_delete_product_image_204_removes_row_and_s3_object(
    client: AsyncClient, minio_ready: None
) -> None:
    _, owner_token = await _register_and_login(client, "delowner2")
    product_id = await _create_product_via_http(client, owner_token)
    upload = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(),
    )
    assert upload.status_code == 201
    storage = get_storage()
    key = f"products/{product_id}/image"

    response = await client.delete(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(owner_token)
    )

    assert response.status_code == 204
    get_after_delete = await client.get(IMAGE_PATH.format(product_id=product_id))
    assert get_after_delete.status_code == 404
    async with storage.client() as s3_client:
        with pytest.raises(ClientError):
            await s3_client.head_object(
                Bucket=settings.minio_bucket_name_product, Key=key
            )


async def test_delete_product_image_403_for_non_owner_non_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_token = await _register_and_login(client, "delowner3")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id)
    _, other_token = await _register_and_login(client, "delother3")

    response = await client.delete(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(other_token)
    )

    assert response.status_code == 403


async def test_delete_product_image_does_not_delete_shared_seed_placeholder(
    client: AsyncClient, db_session: AsyncSession, minio_ready: None
) -> None:
    storage = get_storage()
    await storage.put_object(
        settings.minio_bucket_name_product,
        SEED_PLACEHOLDER_KEY,
        b"placeholder-bytes",
        "image/jpeg",
    )
    _, owner_token = await _register_and_login(client, "delowner4")
    product_id = await _create_product_via_http(client, owner_token)
    await _attach_image(db_session, product_id, s3_key=SEED_PLACEHOLDER_KEY)

    response = await client.delete(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(owner_token)
    )

    assert response.status_code == 204
    async with storage.client() as s3_client:
        await s3_client.head_object(
            Bucket=settings.minio_bucket_name_product, Key=SEED_PLACEHOLDER_KEY
        )


async def test_post_and_delete_product_image_write_audit_log_entries(
    client: AsyncClient, db_session: AsyncSession, minio_ready: None
) -> None:
    owner_id, owner_token = await _register_and_login(client, "auditown1")
    product_id = await _create_product_via_http(client, owner_token)

    await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(),
    )
    await client.delete(
        IMAGE_PATH.format(product_id=product_id), headers=_auth(owner_token)
    )

    logs = (
        await db_session.scalars(
            select(ProductAuditLog)
            .where(ProductAuditLog.product_id == product_id)
            .order_by(ProductAuditLog.created_at, ProductAuditLog.id)
        )
    ).all()
    assert [log.action for log in logs] == [
        ProductAuditAction.CREATED,
        ProductAuditAction.IMAGE_UPDATED,
        ProductAuditAction.IMAGE_DELETED,
    ]
    assert logs[-1].actor_user_id == owner_id
    assert logs[-2].actor_user_id == owner_id


async def test_post_product_image_413_for_oversized_file(
    client: AsyncClient,
) -> None:
    _, owner_token = await _register_and_login(client, "postowner5")
    product_id = await _create_product_via_http(client, owner_token)
    oversized = b"x" * (5 * 1024 * 1024 + 1)

    response = await client.post(
        IMAGE_PATH.format(product_id=product_id),
        headers=_auth(owner_token),
        files=_file(body=oversized),
    )

    assert response.status_code == 413

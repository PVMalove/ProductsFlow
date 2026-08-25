import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProductImage
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

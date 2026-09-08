import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from application.queries.attach_image_urls import attach_image_urls
from contracts.product import ProductView
from domain.product_image import ProductImage
from domain.value_objects.product_id import ProductId


class ImageRepository:
    def __init__(self, image: ProductImage) -> None:
        self._image = image
        self.requested_ids: list[uuid.UUID] = []

    async def get_product_images_by_ids(
        self, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ProductImage]:
        self.requested_ids = list(product_ids)
        return {self._image.product_id.value: self._image}


class ImageStorage:
    async def build_presigned_url(
        self, bucket_name: str, key: str, expires_in: int = 3600
    ) -> str:
        return f"https://storage.test/{bucket_name}/{key}?expires={expires_in}"


async def test_attach_image_urls_batches_and_preserves_no_image() -> None:
    image_product_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    product_without_image_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    image = ProductImage(
        product_id=ProductId.create(image_product_id),
        s3_key="products/one.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repository = ImageRepository(image)
    items = [
        ProductView(
            id=image_product_id,
            name="With image",
            description="",
            price=1,
            category="Tools",
            user_id=uuid.uuid4(),
            is_active=True,
        ),
        ProductView(
            id=product_without_image_id,
            name="Without image",
            description="",
            price=2,
            category="Tools",
            user_id=uuid.uuid4(),
            is_active=True,
        ),
    ]

    attached = await attach_image_urls(
        items,
        repository=repository,
        storage=ImageStorage(),
        bucket_name="product-chunks",
    )

    assert repository.requested_ids == [image_product_id, product_without_image_id]
    assert attached[0].image_url == (
        "https://storage.test/product-chunks/products/one.jpg?expires=3600"
    )
    assert attached[1].image_url is None

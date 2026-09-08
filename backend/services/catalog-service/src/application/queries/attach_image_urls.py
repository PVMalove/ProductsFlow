"""Batched image-URL attachment, shared by list_products и search_products.

Один запрос картинок на всю страницу вместо N (issue: N+1 на каталоге —
каждая карточка дёргала `GET /products/{id}/image` отдельно и упиралась в
gateway rate limit при пагинации), presigned URL строится заново на каждый
ответ (см. `contracts.product.ProductView.image_url`), а не на этапе,
который может закэшироваться.
"""

from dataclasses import replace

from application.ports import ProductImageLookupPort, ProductImageUrlBuilder
from contracts.product import ProductView


async def attach_image_urls(
    items: list[ProductView],
    *,
    repository: ProductImageLookupPort,
    storage: ProductImageUrlBuilder,
    bucket_name: str,
) -> list[ProductView]:
    if not items:
        return items
    images = await repository.get_product_images_by_ids([item.id for item in items])
    if not images:
        return items
    return [
        item
        if (image := images.get(item.id)) is None
        else replace(
            item,
            image_url=await storage.build_presigned_url(bucket_name, image.s3_key),
        )
        for item in items
    ]

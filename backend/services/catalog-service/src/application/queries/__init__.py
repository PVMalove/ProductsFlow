"""Публичный query-side интерфейс для application use case'ов catalog."""

from application.queries.get_product import GetProductQuery, GetProductQueryHandler
from application.queries.get_product_audit import (
    GetProductAuditQuery,
    GetProductAuditQueryHandler,
)
from application.queries.get_product_image import (
    GetProductImageQuery,
    GetProductImageQueryHandler,
)
from application.queries.list_products import (
    ListProductsQuery,
    ListProductsQueryHandler,
)
from application.queries.search_products import (
    SearchProductsQuery,
    SearchProductsQueryHandler,
)

__all__ = [
    "GetProductAuditQuery",
    "GetProductAuditQueryHandler",
    "GetProductImageQuery",
    "GetProductImageQueryHandler",
    "GetProductQuery",
    "GetProductQueryHandler",
    "ListProductsQuery",
    "ListProductsQueryHandler",
    "SearchProductsQuery",
    "SearchProductsQueryHandler",
]

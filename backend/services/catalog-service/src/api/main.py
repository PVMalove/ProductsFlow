from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from kernel_platform.http.exception_handlers import register_error_handlers
from kernel_platform.security.identity_client import IdentityClient
from observability.db_metrics import instrument_sqlalchemy_sessionmaker
from observability.formatters import configure_logging
from observability.metrics import register_exception_metrics, register_http_metrics
from observability.middleware import RequestContextMiddleware
from observability.tracing import (
    instrument_fastapi,
    instrument_httpx,
    instrument_sqlalchemy,
)
from redis.asyncio import Redis

from api.endpoints.product_images import router as product_images_router
from api.endpoints.products import router as products_router
from application.errors import ApplicationError
from core.settings import settings
from infrastructure.db.session import build_sessionmaker
from infrastructure.search.cache import CachedProductSearch
from infrastructure.search.opensearch import OpenSearchProductSearch

configure_logging(settings.app_env, "catalog-service")

# Модульный уровень, не lifespan: RequestContextMiddleware принимает готовый
# экземпляр verifier'а при регистрации (app.add_middleware), до того как
# lifespan вообще запустится — тот же приём, что identity-service применяет
# для LocalTokenVerifier(). httpx.AsyncClient безопасно строить вне event
# loop'а (сами запросы — нет), поэтому конструктор не откладывается.
_identity_http_client = httpx.AsyncClient(base_url=settings.catalog_identity_base_url)
_identity_client = IdentityClient(_identity_http_client)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.sessionmaker = build_sessionmaker(settings.catalog_database_url)
    instrument_sqlalchemy_sessionmaker(
        app, app.state.sessionmaker, service_name="catalog-service"
    )
    instrument_sqlalchemy(app, app.state.sessionmaker)
    app.state.identity_gateway = _identity_client
    search_index = OpenSearchProductSearch(
        base_url=settings.catalog_opensearch_url,
        index_name=settings.catalog_search_index_name,
    )
    redis_client: Redis = Redis.from_url(
        settings.catalog_redis_url, decode_responses=True
    )
    app.state.product_search = CachedProductSearch(
        search_index,
        redis_client,
        ttl_seconds=settings.catalog_search_cache_ttl_seconds,
    )
    await _identity_client.preload()
    try:
        yield
    finally:
        await redis_client.aclose()
        await search_index.close()
        await _identity_http_client.aclose()


app = FastAPI(lifespan=lifespan)
register_error_handlers(
    app,
    service_error_type=ApplicationError,
    on_unhandled_exception=register_exception_metrics("catalog-service"),
)

app.add_middleware(RequestContextMiddleware, verifier=_identity_client)
register_http_metrics(app, service_name="catalog-service")
instrument_fastapi(app, service_name="catalog-service")
instrument_httpx()
app.include_router(products_router)
app.include_router(product_images_router)

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from kernel_platform.http.exception_handlers import register_error_handlers
from kernel_platform.security.identity_client import IdentityClient
from observability.middleware import RequestContextMiddleware

from api.endpoints.product_images import router as product_images_router
from api.endpoints.products import router as products_router
from application.errors import ApplicationError
from core.settings import settings
from infrastructure.db.session import build_sessionmaker

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
    app.state.identity_gateway = _identity_client
    await _identity_client.preload()
    try:
        yield
    finally:
        await _identity_http_client.aclose()


app = FastAPI(lifespan=lifespan)
register_error_handlers(app, service_error_type=ApplicationError)

app.add_middleware(RequestContextMiddleware, verifier=_identity_client)
app.include_router(products_router)
app.include_router(product_images_router)

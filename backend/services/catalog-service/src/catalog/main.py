from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from kernel_platform.security.identity_client import IdentityClient
from observability.middleware import RequestContextMiddleware

from catalog.api.products import router as products_router
from catalog.infrastructure.db.session import build_sessionmaker
from catalog.settings import settings

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
app.add_middleware(RequestContextMiddleware, verifier=_identity_client)
app.include_router(products_router)

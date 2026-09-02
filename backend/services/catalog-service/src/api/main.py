from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from kernel_platform.security.identity_client import IdentityClient
from observability.middleware import RequestContextMiddleware

from api.errors import to_http_exception
from api.product_images import router as product_images_router
from api.products import router as products_router
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


@app.exception_handler(ApplicationError)
async def application_error_handler(
    _request: Request, exc: ApplicationError
) -> JSONResponse:
    error = to_http_exception(exc)
    content = {"detail": error.detail}
    return JSONResponse(status_code=error.status_code, content=content)


app.add_middleware(RequestContextMiddleware, verifier=_identity_client)
app.include_router(products_router)
app.include_router(product_images_router)

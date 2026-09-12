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

from api.endpoints.payments import router as payments_router
from application.errors import ApplicationError
from core.psp import build_psp_client
from core.settings import settings
from infrastructure.db.session import build_sessionmaker

configure_logging(settings.app_env, "payment-service")

# Модульный уровень, не lifespan: RequestContextMiddleware принимает готовый
# экземпляр verifier'а при регистрации (app.add_middleware), до того как
# lifespan вообще запустится — тот же приём, что catalog/inventory-service
# применяют.
_identity_http_client = httpx.AsyncClient(base_url=settings.payment_identity_base_url)
_identity_client = IdentityClient(_identity_http_client)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail-fast: под APP_ENV=prod единственный существующий PspClient
    # (MockPspAdapter) недопустим — реального адаптера не существует
    # (архитектурный бриф D5). Проверяется при старте, не тихим fallback'ом.
    app.state.psp_client = build_psp_client(settings)
    app.state.sessionmaker = build_sessionmaker(settings.payment_database_url)
    instrument_sqlalchemy_sessionmaker(
        app, app.state.sessionmaker, service_name="payment-service"
    )
    instrument_sqlalchemy(app, app.state.sessionmaker)
    app.state.identity_client = _identity_client
    await _identity_client.preload()
    try:
        yield
    finally:
        await _identity_http_client.aclose()


app = FastAPI(title="payment-service", lifespan=lifespan)
register_error_handlers(
    app,
    service_error_type=ApplicationError,
    on_unhandled_exception=register_exception_metrics("payment-service"),
)

app.add_middleware(RequestContextMiddleware, verifier=_identity_client)
register_http_metrics(app, service_name="payment-service")
instrument_fastapi(app, service_name="payment-service")
instrument_httpx()
app.include_router(payments_router)

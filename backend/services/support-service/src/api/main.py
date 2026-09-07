from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel_platform.http.exception_handlers import register_error_handlers
from observability.formatters import configure_logging
from observability.metrics import register_http_metrics
from observability.middleware import RequestContextMiddleware
from observability.tracing import instrument_fastapi

from api.tickets import router as tickets_router
from application.errors import ApplicationError
from core.settings import settings
from infrastructure.db.session import build_sessionmaker

configure_logging(settings.app_env, "support-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.support_database_url:
        app.state.sessionmaker = build_sessionmaker(settings.support_database_url)
    yield


app = FastAPI(title="support-service", lifespan=lifespan)
register_error_handlers(app, service_error_type=ApplicationError)
app.add_middleware(RequestContextMiddleware)
register_http_metrics(app, service_name="support-service")
instrument_fastapi(app, service_name="support-service")
app.include_router(tickets_router)

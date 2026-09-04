from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel_platform.http.exception_handlers import register_error_handlers

from api.tickets import router as tickets_router
from application.errors import ApplicationError
from core.settings import settings
from infrastructure.db.session import build_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.support_database_url:
        app.state.sessionmaker = build_sessionmaker(settings.support_database_url)
    yield


app = FastAPI(title="support-service", lifespan=lifespan)
register_error_handlers(app, service_error_type=ApplicationError)
app.include_router(tickets_router)

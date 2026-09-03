from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel_platform.http.exception_handlers import register_error_handlers
from observability.middleware import RequestContextMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import router as auth_router
from api.jwks import router as jwks_router
from api.users import router as users_router
from application.errors import ApplicationError
from core.logging_config import configure_logging
from core.secrets import validate_prod_key
from core.security.verifier import LocalTokenVerifier
from core.settings import settings

configure_logging(settings.app_env)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_prod_key(settings)
    if not settings.identity_database_url:
        raise RuntimeError("IDENTITY_DATABASE_URL must be configured")
    engine = create_async_engine(settings.identity_database_url)
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
register_error_handlers(app, service_error_type=ApplicationError)
app.add_middleware(RequestContextMiddleware, verifier=LocalTokenVerifier())
app.include_router(jwks_router)
app.include_router(auth_router)
app.include_router(users_router)

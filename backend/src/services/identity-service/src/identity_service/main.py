from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel_platform.logging.middleware import RequestContextMiddleware

from identity_service.api.jwks import router as jwks_router
from identity_service.infrastructure.security.keys import validate_prod_key
from identity_service.infrastructure.security.verifier import LocalTokenVerifier
from identity_service.logging_config import configure_logging
from identity_service.settings import settings

configure_logging(settings.app_env)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_prod_key(settings)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestContextMiddleware, verifier=LocalTokenVerifier())
app.include_router(jwks_router)

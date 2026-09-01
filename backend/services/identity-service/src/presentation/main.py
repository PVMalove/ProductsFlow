from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from observability.middleware import RequestContextMiddleware

from core.logging_config import configure_logging
from core.secrets import validate_prod_key
from core.security.verifier import LocalTokenVerifier
from core.settings import settings
from presentation.jwks import router as jwks_router

configure_logging(settings.app_env)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_prod_key(settings)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestContextMiddleware, verifier=LocalTokenVerifier())
app.include_router(jwks_router)

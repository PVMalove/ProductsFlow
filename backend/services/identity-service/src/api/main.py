from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from observability.middleware import RequestContextMiddleware

from api.jwks import router as jwks_router
from api.mock_me import router as mock_router
from core.logging_config import configure_logging
from core.secrets import validate_prod_key
from core.security.verifier import LocalTokenVerifier
from core.settings import settings

configure_logging(settings.app_env)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_prod_key(settings)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestContextMiddleware, verifier=LocalTokenVerifier())
app.include_router(jwks_router)
app.include_router(mock_router)

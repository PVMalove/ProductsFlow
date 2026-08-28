from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from identity_service.api.jwks import router as jwks_router
from identity_service.infrastructure.security.keys import validate_prod_key
from identity_service.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_prod_key(settings)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(jwks_router)

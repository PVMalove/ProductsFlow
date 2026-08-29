from fastapi import APIRouter

from identity_service.infrastructure.security.keys import (
    build_jwk,
    compute_kid,
    load_private_key,
)
from identity_service.settings import settings

router = APIRouter()


@router.get("/.well-known/jwks.json")
def get_jwks() -> dict[str, list[dict[str, str]]]:
    private_key = load_private_key(settings.identity_jwt_private_key_path)
    public_key = private_key.public_key()
    kid = compute_kid(public_key)
    return {"keys": [build_jwk(public_key, kid)]}

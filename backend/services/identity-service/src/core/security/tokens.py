from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from core.secrets import compute_kid, load_private_key
from core.settings import settings

ALGORITHM = "RS256"
ISSUER = "identity-service"


def create_access_token(sub: UUID) -> str:
    private_key = load_private_key(settings.identity_jwt_private_key_path)
    kid = compute_kid(private_key.public_key())
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int(
            (
                now + timedelta(hours=settings.identity_access_token_ttl_hours)
            ).timestamp()
        ),
        "iss": ISSUER,
    }
    return jwt.encode(payload, private_key, algorithm=ALGORITHM, headers={"kid": kid})


def decode_access_token(token: str) -> dict[str, Any]:
    private_key = load_private_key(settings.identity_jwt_private_key_path)
    return jwt.decode(
        token,
        private_key.public_key(),
        algorithms=[ALGORITHM],
        issuer=ISSUER,
    )

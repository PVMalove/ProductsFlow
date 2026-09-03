"""Shared framework-independent Actor contract (ADR 0033).

`Actor` replaces the identity/support/catalog-local `actor_id`/`is_admin`
pairs and service-local `Actor` duplicates: a security adapter authenticates
the caller and builds this transport-neutral value, while application
handlers own authorization decisions over it."""

import enum
import uuid
from dataclasses import dataclass

from kernel_platform.http.errors import ApiError


class ActorRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


@dataclass(frozen=True)
class Actor:
    """The authenticated caller passed from an HTTP adapter to a use case."""

    id: uuid.UUID
    role: ActorRole


_ADMIN_ONLY = ApiError(
    status_code=403, code="FORBIDDEN", message="Доступ только для администраторов!"
)


def require_admin(actor: Actor) -> Actor:
    """Shared admin-only gate: every service's `AdminActor` FastAPI
    dependency wraps this instead of duplicating the role check and error
    message (ADR 0033)."""
    if actor.role is not ActorRole.ADMIN:
        raise _ADMIN_ONLY
    return actor

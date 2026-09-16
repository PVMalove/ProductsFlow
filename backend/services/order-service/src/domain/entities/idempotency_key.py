"""Idempotency-Key record (issue #372, D2) — plain value, not an `Entity`:
no domain events, no identity-based equality needed beyond its natural key
`(user_id, key)`, enforced at the persistence layer."""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IdempotencyKeyRecord:
    user_id: uuid.UUID
    key: str
    request_fingerprint: str
    order_id: uuid.UUID
    created_at: datetime

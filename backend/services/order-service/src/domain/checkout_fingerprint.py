"""Fingerprint Checkout Selection для Idempotency-Key (issue #372, D2) —
sha256 канонической (сортированной по `line_id`) сериализации
`(line_id, product_id, quantity)` каждой строки корзины. Стабилен к порядку
строк, меняется при изменении состава/количества."""

import hashlib
import json
from collections.abc import Sequence

from domain.entities.cart_line import CartLine


def compute_fingerprint(lines: Sequence[CartLine]) -> str:
    canonical = sorted(
        (str(line.id), str(line.product_id), line.quantity) for line in lines
    )
    serialized = json.dumps(canonical, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()

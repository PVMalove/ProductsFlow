"""Shared constructor-privacy marker for this package's value objects
(Email, RawPassword, UserId) — same scheme as `kernel_domain.Entity`'s
`_PRIVATE_MARKER`, but VOs have no common base `__init__` to enforce it
centrally, so each VO's own `__init__` checks against this one token."""

_PRIVATE_MARKER = object()

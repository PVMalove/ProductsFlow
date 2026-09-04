"""Shared constructor-privacy marker for this package's value objects
(TicketId) and for `TicketMessage` (issue #252, a non-`Entity` child entity
of `Ticket` with no common base `__init__` of its own) — same scheme as
`kernel_domain.Entity`'s `_PRIVATE_MARKER`, but each of these types checks
its own `__init__` against this one token instead of a centralized base."""

_PRIVATE_MARKER = object()

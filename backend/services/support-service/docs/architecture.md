# Architecture

`api` owns external adapters and composition roots (`main.py` and `worker.py`),
`application` owns use cases and ports, `domain` owns support rules, and
`infrastructure` owns persistence and messaging adapters. The service is
independently deployable, with its own `pyproject.toml`, `uv.lock`, and Alembic
migrations.

## CQRS application boundary

The command side currently exposes `CreateTicketCommand` and
`CreateTicketCommandHandler` through `application/commands/`. The handler
creates the Ticket aggregate and delegates the atomic aggregate, first-message
and outbox write to `TicketCommandPort`.

The query side exposes separate handlers in `application/queries/` for getting
one Ticket, listing the caller's Tickets, listing all Tickets for an admin, and
listing a Ticket's messages. They depend only on `TicketQueryPort`, return
read results, and do not mutate aggregates or publish events. HTTP dependencies
construct these handlers from the infrastructure repository while preserving
the existing `api` adapter and routes.

Unread counters, assignment of a staff member, and a local user read model are
outside Phase 5. Request identity and roles come from a locally validated JWT;
the identity-event consumer exists solely to anonymize retained tickets after a
user deletion.

Ticket mutations and their domain events share one database transaction. The
repository writes the existing `kernel_platform.outbox.OutboxMessage` rows;
the installed kernel version has no `OutboxMixin`. The worker records each
identity event in a local inbox in that same transaction, so an at-least-once
RabbitMQ delivery cannot append duplicate system messages.

Ordinary callers receive `404` for tickets they cannot access. All ticket
mutations serialize on the ticket row, including the user-deletion workflow.
Published ticket events contain identifiers, state and actor category, but no
subject or message text.

The Ticket aggregate moves through `OPEN → IN_PROGRESS → RESOLVED → CLOSED`.
A new author message reopens only a resolved Ticket to `IN_PROGRESS`; a closed
Ticket is terminal. Ticket messages are plaintext: a subject has 1–200
characters and a message body has 1–10,000 characters after trimming.

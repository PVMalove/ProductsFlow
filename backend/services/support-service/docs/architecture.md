# Architecture

`api` owns external adapters and composition roots (`main.py` and `worker.py`),
`application` owns use cases and ports, `domain` owns support rules, and
`infrastructure` owns persistence and messaging adapters. The service is
independently deployable, with its own `pyproject.toml`, `uv.lock`, and Alembic
migrations.

## CQRS application boundary

The command side exposes `CreateTicketCommand`, `AddTicketMessageCommand`,
`ChangeTicketStatusCommand`, and `ProcessUserDeletionCommand` with handlers
under `application/commands/`.
Creation uses `TicketCommandPort`; mutations use the separate
`TicketMutationPort`, whose repository adapter locks the ticket row, applies
the domain rule, and commits the aggregate change and outbox rows as one
transaction.

The query side exposes separate handlers in `application/queries/` for getting
one Ticket, listing the caller's Tickets, listing all Tickets for an admin, and
listing a Ticket's messages. They depend only on `TicketQueryPort`, return
read results, and do not mutate aggregates or publish events. HTTP dependencies
construct these handlers from the infrastructure repository while preserving
the existing `api` adapter and routes.

Unread counters, assignment of a staff member, and a local user read model are
outside Phase 5. Request identity and roles come from a locally validated JWT;
the identity-event consumer exists solely to anonymize retained tickets after a
user deletion. `api.worker:main` is its runnable composition root; it declares
the shared `user.*.v1` topology as `support-service.user-events` and uses the
kernel retry ladder.

Ticket mutations and their domain events share one database transaction. The
repository writes the existing `kernel_platform.outbox.OutboxMessage` rows;
the installed kernel version has no `OutboxMixin`. The worker records each
identity event in a local inbox in that same transaction, so an at-least-once
RabbitMQ delivery cannot append duplicate system messages.

Ordinary callers receive `404` for tickets they cannot access. All ticket
mutations serialize on the ticket row, including the user-deletion workflow.
Published ticket events contain identifiers, state and actor category, but no
subject or message text.

The worker inserts the incoming outbox message id into the service-local
`processed_messages` inbox before changing tickets. The receipt, nullable
author links, closure, system message, and technical outbox rows commit as one
transaction. Repeated delivery therefore produces no second system message;
active tickets receive one immutable `[Пользователь удалён]` note, while already
closed tickets are only anonymized.

The Ticket aggregate moves through `OPEN → IN_PROGRESS → RESOLVED → CLOSED`.
A new author message reopens only a resolved Ticket to `IN_PROGRESS`; a closed
Ticket is terminal. Ticket messages are plaintext: a subject has 1–200
characters and a message body has 1–10,000 characters after trimming.
Normal status commands can only move one step forward through the lifecycle.
User message access is owner-scoped, while an admin may append to any
non-closed Ticket and advance its status. The repository uses a `FOR UPDATE`
ticket-row lock so concurrent mutations observe one serialized state.

## BFF migration (ADR 0033)

`api.worker` now maintains a full local user projection
(`infrastructure/db/user_projection.py`), not just the deletion inbox: it
consumes all five `user.*.v1` events and applies each one with the same
`last_applied_outbox_id` version guard as catalog's `owner_read_model`
(ADR 0019), independent of the separate `processed_messages` inbox that
still guards ticket anonymization on `user.deleted.v1` specifically —
sharing one inbox row across both concerns would make the anonymization
insert see its own already-inserted row and skip. Deletion sets `deleted`
(tombstone) and `is_active=False`; the version guard means a stale or
replayed event can never revive it.

`infrastructure/security/auth.py` builds `kernel_platform.security.Actor`
from that projection instead of trusting JWT claims: `_verify_token` decodes
and validates the JWT with no DB access (so a missing/invalid token never
opens a database session), then `get_current_actor` looks up the caller by
id — a missing row is `401`, an inactive or tombstoned one is `403`.
`RequiredActor`/`AdminActor` replace the old `RequiredAuth`/`AdminAuth`
UUID-only dependencies.

`api/tickets.py` is thin: `api/schemas.py` request/dependency models build
commands and queries via `to_command()`/`to_query()`, and
`kernel_platform.http.match.match_result`/`match_created` wrap application
`Result`s into the shared `ApiResponse` envelope. The four mutation command
handlers (`add_ticket_message`, `change_ticket_status`,
`edit_ticket_message`, `delete_ticket_message`) now catch the `Ticket`
aggregate's domain exceptions and the `None`-for-not-found/not-owned
repository result themselves, returning `Result` — routers no longer
translate errors. `application/queries/get_ticket_detail.py` is the single
combined query the endpoint calls for `GET /{ticket_id}`: it loads the
ticket and its first page of messages together, so the endpoint never
orchestrates two handler calls. Every `DELETE` returns `200` with
`data: null`; list and detail pagination live only in the root `meta`, not
nested under `data`.

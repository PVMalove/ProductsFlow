# API

The support HTTP surface is designed in the Phase 5 domain session.
`api.main:app` is the service entrypoint.

- `POST /api/v1/tickets` creates a Ticket and its required first message.
- `GET /api/v1/tickets` lists the caller's Tickets with a keyset cursor.
- `GET /api/v1/admin/tickets` lists every Ticket for an `admin` actor.
- `POST /api/v1/tickets/{ticket_id}/messages` appends a message.
- `GET /api/v1/tickets/{ticket_id}` returns an accessible Ticket and a
  cursor-paginated message thread.
- `PATCH /api/v1/tickets/{ticket_id}/messages/{message_id}` edits the caller's
  own non-deleted message before the Ticket is closed.
- `DELETE /api/v1/tickets/{ticket_id}/messages/{message_id}` soft-deletes a
  message; an `admin` may use it for moderation.
- `PATCH /api/v1/tickets/{ticket_id}/status` changes a Ticket status.

Appending a message returns the updated Ticket with `201`. A normal caller may
append only to their own non-closed Ticket; an administrator may append to any
non-closed Ticket. Status changes require an administrator and return the
updated Ticket with `200`. Invalid lifecycle transitions and attempts to
mutate a closed Ticket return `409`; an inaccessible Ticket is reported as
`404`.

Tickets themselves are neither edited nor deleted in Phase 5. Message editing
and deletion are separate operations whose authorization and retention rules
are defined above. Message edits and soft deletions publish
`ticket.message_edited.v1` and `ticket.message_deleted.v1` without text.

All text is trimmed plaintext: subjects contain 1–200 characters and message
bodies contain 1–10,000; invalid input returns `422`. A system message cannot
be edited or deleted. An inaccessible Ticket is reported as `404` to an
ordinary caller. Ticket lists are newest-first by `(created_at, id)` and
message threads oldest-first by the same composite key; their opaque cursors
encode both values.

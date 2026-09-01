# identity-service

Independently deployable identity API and outbox worker. The service follows
the canonical layout in repository ADR 0026; shared code is imported from
`backend/libs/`.

Run checks and tests from `backend/` with `make check pkg=identity-service`
and `make test pkg=identity-service`.

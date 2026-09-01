# Architecture

`api` owns HTTP and worker entrypoints, `application` owns use cases,
`domain` owns identity business concepts, `infrastructure` owns persistence,
and `core` owns service-local security and configuration policy.

## CQRS application boundary

Identity writes are defined in `application/commands/`, with one module per
related operation and immutable command DTOs plus dedicated command handlers.
The package `__init__.py` is the public command-side facade. Handlers depend on the domain-owned
`UserRepository` contract and `PasswordHasher`; concrete persistence and hashing adapters stay outside the
application layer. Registration, login, password changes, and activation or
deactivation therefore retain their existing domain and outbox contracts while
having an explicit command-side seam.

Identity reads use immutable DTOs in `application/queries.py` and
`GetUserQueryHandler`, which accepts only `UserQueryPort`. The query port has
no `add` or `save` operation, so a query handler cannot accidentally mutate the
aggregate through its declared dependency. The old per-operation module paths
remain thin re-export adapters for callers during the migration.

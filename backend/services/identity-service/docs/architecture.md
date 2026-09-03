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

Identity reads use immutable DTOs in `application/queries/`, with one module per
query and a package-level public facade. `GetUserQueryHandler` accepts only
`UserQueryPort`. The query port has
no `add` or `save` operation, so a query handler cannot accidentally mutate the
aggregate through its declared dependency. The old per-operation module paths
remain thin re-export adapters for callers during the migration.

`ListUsersQueryHandler` reads an administrator's cursor-paginated `UserPage`
through `UserListQueryPort`, using the shared `kernel_platform.pagination`
contract. `GetUserAuditQueryHandler` uses `UserAuditQueryPort`: a missing
`user_id` selects the global offset-paginated `UserAuditPage` with
`page_index`/`page_size` and `total_pages`, while a supplied `user_id` selects
the complete, unpaginated personal history. Authorization and the distinction
between the caller's own id and an administrator's target id belong to the API
boundary.

`infrastructure.db.user_repository.UserRepository` maps the aggregate to the
SQLAlchemy `UserModel`. Every mutating method drains domain events through the
shared kernel-platform outbox operation and commits once, so the user row and
its outbox rows share one transaction. ORM listeners in `infrastructure.db.audit`
write the immutable user audit trail and resolve the actor from the shared
request `ContextVar` (falling back to the affected user's id outside HTTP).
`SqlUserQueryRepository` and `SqlUserAuditReader` provide the corresponding
read-side SQL adapters without exposing password hashes.

## BFF migration (ADR 0033)

`api/users.py` and `/api/v1/auth/register` are thin: `api/schemas.py`
dependency models turn the request into a command/query via
`to_command()`/`to_query()`, and `kernel_platform.http.match.match_result`/
`match_created` wrap the application `Result` into the shared `ApiResponse`
envelope. `api/security.py` decodes the bearer JWT, reloads the caller
through `UserQueryPort` and returns a `kernel_platform.security.Actor` — the
same reload also enforces `is_active` for every authenticated identity
endpoint, not only `/users/me`. `GetCurrentUserHandler`
(`application/queries/get_current_user.py`) is the dedicated `/users/me`
read path: it reloads the caller's row again and returns
`contracts.user.UserView`, so the response never trusts JWT claims.
`GetUserAuditQueryHandler` now takes both `UserAuditQueryPort` and
`UserQueryPort`, returning `Result` and failing `NOT_FOUND` for an unknown
target user instead of leaving that check to the router. `/api/v1/auth/login`
keeps its flat OAuth2 password-grant response — the ADR excludes it from the
envelope so `OAuth2PasswordBearer`/Swagger UI keep working unchanged.

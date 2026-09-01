# Architecture

`api` owns HTTP entrypoints, schemas, and the FastAPI composition
root. Product HTTP handlers only translate requests and responses. Product
commands live one-per-operation under `src/application/commands/` and product
queries live one-per-operation under `src/application/queries/`. Each operation
has an immutable DTO and a dedicated handler with a `handle()` entrypoint.
The former `product_use_cases.py` and `product_image_use_cases.py` compatibility
modules were removed after the CQRS migration. Callers use the public command
and query package facades directly.

Application code depends on explicit command/query ports for product access and
on ports for the owner read model, identity lookup, image storage, and audit
reads. Command handlers own mutations and query handlers own visibility,
pagination, audit, and image reads.
`ProductVisibilityPolicy` remains in `domain`. SQLAlchemy implementations are
assembled only in `api/dependencies.py`, while `api` maps
application errors to the unchanged HTTP status and response contract.

The same `api` layer owns `api.worker`, the second process of
the catalog service image (ADR 0010). It declares the `catalog.user-events`
topology through `kernel-platform`, consumes the four supported `user.*.v1`
events (including the sparse payloads emitted by the current identity domain),
and applies each owner snapshot with the inbox/version guards from ADR 0019.

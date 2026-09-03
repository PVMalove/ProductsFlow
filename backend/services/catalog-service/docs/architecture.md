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

Command handlers load an aggregate through `ProductCommandPort` when they need
to authorize or validate a mutation. They do not cast the repository to
`ProductQueryPort`; query ports are reserved for query handlers. The former
mixed `product_use_cases.py` and `product_image_use_cases.py` facades are
removed and must not be reintroduced as compatibility adapters.
`ProductVisibilityPolicy` remains in `domain`. SQLAlchemy implementations are
assembled only in `api/dependencies.py`, while `api` maps
application errors to the unchanged HTTP status and response contract.

The same `api` layer owns `api.worker`, the second process of
the catalog service image (ADR 0010). It declares the `catalog.user-events`
topology through `kernel-platform`, consumes the four supported `user.*.v1`
events (including the sparse payloads emitted by the current identity domain),
and applies each owner snapshot with the inbox/version guards from ADR 0019.

`api/product_images.py` (ADR 0033) follows the same shape as `products.py`:
`api/schemas.py` request models (`ProductImageGetRequest`,
`ProductImageUploadRequest`, `ProductImageDeleteRequest`) own all transport
validation — including `ProductImageUploadRequest.to_command()`'s content-type
and size checks, now `ProductImageUnsupportedMediaTypeError`/
`ProductImageTooLargeError` (`application/errors.py`) instead of a raw
`HTTPException` in the router — and the three image handlers return
`Result[ProductImageView]`/`Result[ProductImageMutation]`/`Result[None]`,
unwrapped by `match_result` exactly like `get_product`/`activate_product`.
`GetProductImageQueryHandler` and the two mutation handlers keep the existing
`raise ProductNotFoundError`/`ProductImageNotFoundError` shortcuts for the
not-found/not-visible paths — the same hybrid raise-for-absence,
`Result`-for-success shape `get_product.py` already uses. `DELETE` returns
`200` with `data: null`. The upload endpoint still calls
`UpsertProductImageCommandHandler` and then `GetProductImageQueryHandler` as
two separate handler calls — not the router-orchestration ADR 0033 forbids
elsewhere, since `ProductImageMutation` deliberately carries only
`replaced: bool` and never a query-side View (command/query separation this
codebase already tests for); the small `_unwrap()` helper in
`product_images.py` exists only because the upload response needs the
mutation's `replaced` flag to pick a status code before the second call, a
shape `match_result` doesn't fit.

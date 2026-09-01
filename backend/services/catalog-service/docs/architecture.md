# Architecture

`presentation` owns HTTP entrypoints, schemas, and the FastAPI composition
root. Product HTTP handlers only translate requests and responses; the eight
product use cases live in `src/application/product_use_cases.py`:
`CreateProduct`, `ListProducts`, `GetProduct`, `UpdateProduct`,
`ActivateProduct`, `DeactivateProduct`, `DeleteProduct`, and
`GetProductAudit`.

Application code depends on `ProductRepository` from `domain.repositories` and
on explicit ports for the owner read model, identity lookup, and audit reads.
`ProductVisibilityPolicy` remains in `domain`. SQLAlchemy implementations are
assembled only in `presentation/dependencies.py`, while `presentation` maps
application errors to the unchanged HTTP status and response contract.

The same `presentation` layer owns `presentation.worker`, the second process of
the catalog image (ADR 0010). It declares the `catalog.user-events` topology
through `kernel-platform`, consumes the four supported `user.*.v1` events, and
applies each owner snapshot with the inbox/version guards from ADR 0019.

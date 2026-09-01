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

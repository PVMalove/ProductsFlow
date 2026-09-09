# 0017. Dependency Injector composition roots and request-scoped database sessions

**Status:** Accepted.

Each bounded context owns a declarative `dependency-injector` container in `core/container.py`; `kernel-platform` provides neither a shared container nor a shared service graph. A container receives its service's Pydantic settings through `Configuration` and owns process-scoped resources (connection pools, reusable infrastructure clients and worker-only connections), while FastAPI creates exactly one `AsyncSession` per HTTP request and shares it through that request's handler/repository/UoW graph. A session must never be initialized as a container-wide `Resource`: that would cross transaction boundaries and permit concurrent requests to share mutable SQLAlchemy state. HTTP token parsing remains a FastAPI concern; clients it needs are supplied by the container. All entrypoints use the same composition root but initialize only their context-specific resource group; the migration preserves existing connectivity/readiness behaviour.

## Consequences

Endpoints receive application handlers through `@inject` and `Depends(Provide[Container.*])`; mutable `app.state` is not an application dependency registry. Application factories accept a container so tests override providers instead of mutating FastAPI dependencies or global state. The request-scope adapter is retained solely to give FastAPI an async-generator teardown boundary; it is not a hand-written application dependency chain.

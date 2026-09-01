# catalog-service

Independently deployable catalog API. The service follows the canonical layout
in repository ADR 0026; shared code is imported from `backend/libs/`.

Run checks and tests from `backend/` with `make check pkg=catalog-service`
and `make test pkg=catalog-service`.

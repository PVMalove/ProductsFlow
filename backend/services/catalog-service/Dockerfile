FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY libs/kernel-domain/pyproject.toml libs/kernel-domain/
COPY libs/kernel-platform/pyproject.toml libs/kernel-platform/
COPY libs/observability/pyproject.toml libs/observability/
COPY libs/test-support/pyproject.toml libs/test-support/
COPY services/identity-service/pyproject.toml services/identity-service/
COPY services/catalog-service/pyproject.toml services/catalog-service/
COPY services/support-service/pyproject.toml services/support-service/

RUN uv sync --package catalog-service --locked --no-dev --no-install-project

COPY libs/kernel-domain/src libs/kernel-domain/src
COPY libs/kernel-platform/src libs/kernel-platform/src
COPY libs/observability/src libs/observability/src
COPY services/catalog-service/src services/catalog-service/src
COPY services/catalog-service/assets services/catalog-service/assets
RUN uv sync --package catalog-service --locked --no-dev

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/.venv /srv/.venv
COPY --from=builder /srv/services/catalog-service/src/infrastructure/db /srv/infrastructure/db
# catalog-bootstrap (issue #208) reads this relative to WORKDIR, same as the
# `infrastructure/db` copy above.
COPY --from=builder /srv/services/catalog-service/assets /srv/assets
COPY --from=builder /srv/services/catalog-service/src /srv/services/catalog-service/src
ENV PATH="/srv/.venv/bin:$PATH"
ENV PYTHONPATH="/srv/services/catalog-service/src"

# HTTP entrypoint is provided by the service API package.
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

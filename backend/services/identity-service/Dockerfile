FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY libs/kernel-domain/pyproject.toml libs/kernel-domain/pyproject.toml
COPY libs/kernel-platform/pyproject.toml libs/kernel-platform/pyproject.toml
COPY libs/observability/pyproject.toml libs/observability/pyproject.toml
COPY services/identity-service/pyproject.toml services/identity-service/uv.lock services/identity-service/
WORKDIR /srv/services/identity-service
RUN uv sync --locked --no-dev --no-install-project

COPY libs/kernel-platform/src /srv/libs/kernel-platform/src
COPY libs/observability/src /srv/libs/observability/src
COPY services/identity-service/src /srv/services/identity-service/src
COPY services/identity-service/alembic.ini /srv/services/identity-service/alembic.ini
COPY services/identity-service/alembic /srv/services/identity-service/alembic
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/services/identity-service/.venv /srv/.venv
COPY --from=builder /srv/services/identity-service/alembic.ini alembic.ini
COPY --from=builder /srv/services/identity-service/alembic alembic
ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "identity.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

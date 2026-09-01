FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY libs/kernel-domain/pyproject.toml libs/kernel-domain/pyproject.toml
COPY libs/kernel-platform/pyproject.toml libs/kernel-platform/pyproject.toml
COPY libs/observability/pyproject.toml libs/observability/pyproject.toml
COPY services/identity-service/pyproject.toml services/identity-service/uv.lock services/identity-service/
WORKDIR /srv/services/identity-service
RUN uv sync --locked --no-dev --no-install-project

COPY libs/kernel-platform/src /srv/libs/kernel-platform/src
COPY libs/kernel-domain/src /srv/libs/kernel-domain/src
COPY libs/observability/src /srv/libs/observability/src
COPY services/identity-service/src /srv/services/identity-service/src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/services/identity-service/.venv /srv/services/identity-service/.venv
COPY --from=builder /srv/services/identity-service/src/infrastructure/db /srv/infrastructure/db
ENV PATH="/srv/services/identity-service/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "presentation.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

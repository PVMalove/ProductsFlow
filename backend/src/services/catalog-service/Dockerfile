FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY src/libs/kernel-domain/pyproject.toml src/libs/kernel-domain/pyproject.toml
COPY src/libs/kernel-platform/pyproject.toml src/libs/kernel-platform/pyproject.toml
COPY src/services/identity-service/pyproject.toml src/services/identity-service/pyproject.toml
COPY src/services/catalog-service/pyproject.toml src/services/catalog-service/pyproject.toml
COPY src/services/support-service/pyproject.toml src/services/support-service/pyproject.toml
RUN uv sync --locked --package catalog-service --no-dev --no-install-project

COPY src/services/catalog-service/src src/services/catalog-service/src
RUN uv sync --locked --package catalog-service --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/.venv /srv/.venv
ENV PATH="/srv/.venv/bin:$PATH"

# main.py и uvicorn как зависимость появятся вместе с доменным кодом сервиса —
# до этого момента CMD ниже нерабочий (это ожидаемо для каркасного тикета #74).
EXPOSE 8000
CMD ["uvicorn", "catalog_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

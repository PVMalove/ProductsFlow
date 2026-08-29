FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY src/libs/kernel-domain/pyproject.toml src/libs/kernel-domain/pyproject.toml
COPY src/libs/kernel-platform/pyproject.toml src/libs/kernel-platform/pyproject.toml
COPY src/services/identity-service/pyproject.toml src/services/identity-service/pyproject.toml
COPY src/services/catalog-service/pyproject.toml src/services/catalog-service/pyproject.toml
COPY src/services/support-service/pyproject.toml src/services/support-service/pyproject.toml
RUN uv sync --locked --package identity-service --no-dev --no-install-project

COPY src/libs/kernel-platform/src src/libs/kernel-platform/src
COPY src/services/identity-service/src src/services/identity-service/src
COPY src/services/identity-service/alembic.ini src/services/identity-service/alembic.ini
COPY src/services/identity-service/alembic src/services/identity-service/alembic
RUN uv sync --locked --package identity-service --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/.venv /srv/.venv
COPY --from=builder /srv/src/services/identity-service/alembic.ini src/services/identity-service/alembic.ini
COPY --from=builder /srv/src/services/identity-service/alembic src/services/identity-service/alembic
ENV PATH="/srv/.venv/bin:$PATH"

# main.py и uvicorn как зависимость появятся вместе с доменным кодом сервиса —
# до этого момента CMD ниже нерабочий (это ожидаемо для каркасного тикета #74).
EXPOSE 8000
CMD ["uvicorn", "identity_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

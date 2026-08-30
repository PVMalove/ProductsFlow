FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY libs/kernel-domain/pyproject.toml libs/kernel-domain/pyproject.toml
COPY libs/kernel-platform/pyproject.toml libs/kernel-platform/pyproject.toml
COPY libs/observability/pyproject.toml libs/observability/pyproject.toml
# test-support — dev-only (тесты, ADR 0018), но `uv sync --locked` всё равно
# резолвит метаданные всех путей из [tool.uv.sources] независимо от
# --no-dev, поэтому нужен и здесь.
COPY libs/test-support/pyproject.toml libs/test-support/pyproject.toml
COPY services/catalog-service/pyproject.toml services/catalog-service/uv.lock services/catalog-service/
WORKDIR /srv/services/catalog-service
RUN uv sync --locked --no-dev --no-install-project

COPY libs/kernel-domain/src /srv/libs/kernel-domain/src
COPY libs/kernel-platform/src /srv/libs/kernel-platform/src
COPY libs/observability/src /srv/libs/observability/src
COPY services/catalog-service/src /srv/services/catalog-service/src
COPY services/catalog-service/alembic.ini /srv/services/catalog-service/alembic.ini
COPY services/catalog-service/alembic /srv/services/catalog-service/alembic
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/services/catalog-service/.venv /srv/.venv
COPY --from=builder /srv/services/catalog-service/alembic.ini alembic.ini
COPY --from=builder /srv/services/catalog-service/alembic alembic
ENV PATH="/srv/.venv/bin:$PATH"

# main.py и uvicorn/fastapi как зависимость появятся вместе с HTTP-слоем
# сервиса (issue #149) — до этого момента CMD ниже нерабочий (это ожидаемо,
# доменный/персистентностный код issue #148 не включает HTTP-слой).
EXPOSE 8000
CMD ["uvicorn", "catalog.main:app", "--host", "0.0.0.0", "--port", "8000"]

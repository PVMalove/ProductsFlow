FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY services/support-service/pyproject.toml services/support-service/uv.lock services/support-service/
COPY libs/kernel-domain /srv/libs/kernel-domain
COPY libs/kernel-platform /srv/libs/kernel-platform
# uv resolves path sources even when the dependency is excluded by --no-dev.
COPY libs/test-support/pyproject.toml libs/test-support/pyproject.toml
WORKDIR /srv/services/support-service
RUN uv sync --locked --no-dev --no-install-project

COPY services/support-service/src /srv/services/support-service/src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/services/support-service/.venv /srv/services/support-service/.venv
ENV PATH="/srv/services/support-service/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

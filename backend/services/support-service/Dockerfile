FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /srv

COPY services/support-service/pyproject.toml services/support-service/uv.lock services/support-service/
WORKDIR /srv/services/support-service
RUN uv sync --locked --no-dev --no-install-project

COPY services/support-service/src /srv/services/support-service/src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /srv

COPY --from=builder /srv/services/support-service/.venv /srv/.venv
ENV PATH="/srv/.venv/bin:$PATH"

# main.py и uvicorn как зависимость появятся вместе с доменным кодом сервиса —
# до этого момента CMD ниже нерабочий (это ожидаемо для каркасного тикета #74).
EXPOSE 8000
CMD ["uvicorn", "support.main:app", "--host", "0.0.0.0", "--port", "8000"]

.DEFAULT_GOAL := help

# На Windows заставляем make всегда идти через cmd.exe — см. корневой Makefile
# (без этого .cmd/.bat-обёртки вроде mypy не находятся через PATH/PATHEXT).
ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
endif
.PHONY: check test format lint build up_dev up_prod keys \
	db-revision db-upgrade db-downgrade db-current db-history help _require-pkg

# ---- Переменные по умолчанию (можно переопределить: make check pkg=identity-service) ----
pkg ?=
service ?=

member_dir = $(firstword $(wildcard src/libs/$(pkg)) $(wildcard src/services/$(pkg)))

_require-pkg:
	$(if $(pkg),,$(error pkg не задан — использование: make check pkg=<member>))

check: _require-pkg ## Прогнать все линтеры на члене workspace (make check pkg=<member>)
	uv run --package $(pkg) ruff check $(member_dir)
	uv run --package $(pkg) mypy --explicit-package-bases $(member_dir)
	uv run --package $(pkg) ruff format --check $(member_dir)
	uv run --package $(pkg) vulture whitelist.py $(member_dir)

format: _require-pkg ## Автоформатирование кода члена workspace (ruff format + ruff check --fix)
	uv run --package $(pkg) ruff format $(member_dir)
	uv run --package $(pkg) ruff check --fix $(member_dir)

lint: format check ## Сначала отформатировать, затем проверить (format + check)

test: _require-pkg ## Прогнать тесты члена workspace (make test pkg=<member>)
	uv run --package $(pkg) pytest $(member_dir)

build: ## Пересобрать образы docker compose (make build service=identity-api)
	docker compose build $(service)

keys: ## Сгенерировать локальную RS256-пару для identity (ADR 0011, dev-only, не в git)
	uv run --package identity-service python scripts/generate_dev_keys.py

db-revision: _require-pkg ## Создать ревизию через autogenerate (make db-revision pkg=<service> msg="add foo")
	uv run --package $(pkg) alembic -c $(member_dir)/alembic.ini revision --autogenerate -m "$(msg)"

db-upgrade: _require-pkg ## Применить все непримененные миграции сервиса до head (make db-upgrade pkg=<service>)
	uv run --package $(pkg) alembic -c $(member_dir)/alembic.ini upgrade head

db-downgrade: _require-pkg ## Откатить последнюю миграцию сервиса на один шаг (make db-downgrade pkg=<service>)
	uv run --package $(pkg) alembic -c $(member_dir)/alembic.ini downgrade -1

db-current: _require-pkg ## Показать текущую ревизию БД сервиса (make db-current pkg=<service>)
	uv run --package $(pkg) alembic -c $(member_dir)/alembic.ini current

db-history: _require-pkg ## Показать всю историю миграций сервиса (make db-history pkg=<service>)
	uv run --package $(pkg) alembic -c $(member_dir)/alembic.ini history

up_dev: ## Поднять dev-конфигурацию (docker-compose.yml + docker-compose.dev.yml; make up_dev service=identity-api)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d $(service)

up_prod: ## Поднять prod-конфигурацию (docker-compose.yml + docker-compose.prod.yml; make up_prod service=identity-api)
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build $(service)

help: ## Показать список команд с описанием
	@python -c "import re, sys; print('Доступные команды:'); lines = open(sys.argv[1], encoding='utf-8').readlines(); matches = [re.match(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', line) for line in lines]; [print(f'  {m.group(1):<16} - {m.group(2)}') for m in matches if m]" $(MAKEFILE_LIST)
	@python -c "print()"
	@echo Переменные (переопределяются так: make [команда] [переменная]=[значение]):
	@echo   pkg     - имя члена workspace для check/format/lint/test/db-* (текущее: $(pkg))
	@echo   service - имя compose-сервиса для build/up_dev/up_prod (текущее: $(service))

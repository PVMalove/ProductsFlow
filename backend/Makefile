.DEFAULT_GOAL := help

# На Windows заставляем make всегда идти через cmd.exe — см. корневой Makefile
# (без этого .cmd/.bat-обёртки вроде mypy не находятся через PATH/PATHEXT).
ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
endif
.PHONY: check test format lint architecture-check build up_dev up_prod keys \
	setup demo \
	db-revision db-upgrade db-downgrade db-current db-history help _require-pkg

# ---- Переменные по умолчанию (можно переопределить: make check pkg=identity-service) ----
pkg ?=
service ?=

member_dir = $(firstword $(wildcard libs/$(pkg)) $(wildcard services/$(pkg)))

_require-pkg:
	$(if $(pkg),,$(error pkg не задан — использование: make check pkg=<member>))
	$(if $(member_dir),,$(error пакет '$(pkg)' не найден ни в libs/, ни в services/))

architecture-check: ## Проверить направление зависимостей и вывести CQRS-аудит
	python scripts/check_architecture.py --strict

# mypy запускается из backend/ с путём пакета. Не передаём
# --explicit-package-bases: для пакетов с валидным путём, например
# libs/observability, этот флаг создаёт второе имя модуля
# (libs.observability.src.*) наряду с именем editable-инсталляции.
check: _require-pkg ## Прогнать все линтеры на пакете (make check pkg=<member>) — своё изолированное окружение
	cd $(member_dir) && uv sync --all-packages
	cd $(member_dir) && uv run ruff check .
	cd $(member_dir) && uv run mypy --cache-dir .mypy_cache .
	cd $(member_dir) && uv run ruff format --check .
	cd $(member_dir) && uv run vulture ../../whitelist.py .

format: _require-pkg ## Автоформатирование кода пакета (ruff format + ruff check --fix)
	cd $(member_dir) && uv sync --all-packages
	cd $(member_dir) && uv run ruff format .
	cd $(member_dir) && uv run ruff check --fix .

lint: format check ## Сначала отформатировать, затем проверить (format + check)

test: _require-pkg ## Прогнать тесты пакета (make test pkg=<member>)
	cd $(member_dir) && uv sync --all-packages
	cd $(member_dir) && uv run pytest .

build: ## Пересобрать образы docker compose (make build service=identity-api)
	docker compose build $(service)

keys: ## Сгенерировать локальную RS256-пару для identity (ADR 0011, dev-only, не в git)
	cd services/identity-service && uv sync
	cd services/identity-service && uv run python ../../scripts/generate_dev_keys.py

db-revision: _require-pkg ## Создать ревизию через autogenerate (make db-revision pkg=<service> msg="add foo")
	cd $(member_dir) && uv sync
	cd $(member_dir) && uv run alembic -c src/infrastructure/db/alembic.ini revision --autogenerate -m "$(msg)"

db-upgrade: _require-pkg ## Применить все непримененные миграции сервиса до head (make db-upgrade pkg=<service>)
	cd $(member_dir) && uv sync
	cd $(member_dir) && uv run alembic -c src/infrastructure/db/alembic.ini upgrade head

db-downgrade: _require-pkg ## Откатить последнюю миграцию сервиса на один шаг (make db-downgrade pkg=<service>)
	cd $(member_dir) && uv sync
	cd $(member_dir) && uv run alembic -c src/infrastructure/db/alembic.ini downgrade -1

db-current: _require-pkg ## Показать текущую ревизию БД сервиса (make db-current pkg=<service>)
	cd $(member_dir) && uv sync
	cd $(member_dir) && uv run alembic -c src/infrastructure/db/alembic.ini current

db-history: _require-pkg ## Показать всю историю миграций сервиса (make db-history pkg=<service>)
	cd $(member_dir) && uv sync
	cd $(member_dir) && uv run alembic -c src/infrastructure/db/alembic.ini history

up_dev: ## Поднять dev-конфигурацию (docker-compose.yml + docker-compose.dev.yml; make up_dev service=identity-api)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d $(service)

up_prod: ## Поднять prod-конфигурацию (docker-compose.yml + docker-compose.prod.yml; make up_prod service=identity-api)
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build $(service)

setup: ## Поднять *-db + MinIO + RabbitMQ, дождаться health, прогнать миграции всех *-bootstrap (без сида, без *-api/*-worker)
	docker compose up -d --wait identity-db catalog-db support-db minio rabbitmq
	docker compose run --rm --no-deps identity-bootstrap alembic -c infrastructure/db/alembic.ini upgrade head
	docker compose run --rm --no-deps catalog-bootstrap alembic -c infrastructure/db/alembic.ini upgrade head
	docker compose run --rm --no-deps support-bootstrap alembic -c infrastructure/db/alembic.ini upgrade head

demo: setup ## setup + сид каждого сервиса (супер-админ, 360 товаров через identity-worker/catalog-worker, connectivity-check support)
	docker compose run --rm --no-deps identity-bootstrap python -m api.bootstrap
	docker compose up -d --wait --no-deps identity-worker catalog-worker
	docker compose run --rm --no-deps catalog-bootstrap python -m api.bootstrap
	docker compose run --rm --no-deps support-bootstrap python -m api.bootstrap

help: ## Показать список команд с описанием
	@python -c "import re, sys; print('Доступные команды:'); lines = open(sys.argv[1], encoding='utf-8').readlines(); matches = [re.match(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', line) for line in lines]; [print(f'  {m.group(1):<16} - {m.group(2)}') for m in matches if m]" $(MAKEFILE_LIST)
	@python -c "print()"
	@echo Переменные (переопределяются так: make [команда] [переменная]=[значение]):
	@echo   pkg     - имя члена workspace для check/format/lint/test/db-* (текущее: $(pkg))
	@echo   service - имя compose-сервиса для build/up_dev/up_prod (текущее: $(service))

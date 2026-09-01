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

member_dir = $(firstword $(wildcard libs/$(pkg)) $(wildcard services/$(pkg)))

_require-pkg:
	$(if $(pkg),,$(error pkg не задан — использование: make check pkg=<member>))
	$(if $(member_dir),,$(error пакет '$(pkg)' не найден ни в libs/, ни в services/))

# uv run --project <dir> из backend/ (а не `cd <dir> && uv run`): mypy
# --explicit-package-bases выводит имя модуля из позиционного пути относительно
# cwd, и при cwd=<dir> путь "src" — валидный идентификатор, из-за чего
# value_object.py находится дважды под разными именами модуля
# ("src.kernel_domain.value_object" и "kernel_domain.value_object" через
# editable-инсталл в .venv). При cwd=backend/ путь "libs/kernel-domain/src"
# содержит дефис ("kernel-domain"), который обрывает сборку dotted-имени, и
# конфликта не возникает.
check: _require-pkg ## Прогнать все линтеры на пакете (make check pkg=<member>) — своё изолированное окружение
	uv --project $(member_dir) sync
	uv run --project $(member_dir) ruff check $(member_dir)
	uv run --project $(member_dir) mypy --explicit-package-bases $(member_dir)
	uv run --project $(member_dir) ruff format --check $(member_dir)
	uv run --project $(member_dir) vulture whitelist.py $(member_dir)

format: _require-pkg ## Автоформатирование кода пакета (ruff format + ruff check --fix)
	uv --project $(member_dir) sync
	uv run --project $(member_dir) ruff format $(member_dir)
	uv run --project $(member_dir) ruff check --fix $(member_dir)

lint: format check ## Сначала отформатировать, затем проверить (format + check)

test: _require-pkg ## Прогнать тесты пакета (make test pkg=<member>)
	uv --project $(member_dir) sync
	uv run --project $(member_dir) pytest $(member_dir)

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

help: ## Показать список команд с описанием
	@python -c "import re, sys; print('Доступные команды:'); lines = open(sys.argv[1], encoding='utf-8').readlines(); matches = [re.match(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', line) for line in lines]; [print(f'  {m.group(1):<16} - {m.group(2)}') for m in matches if m]" $(MAKEFILE_LIST)
	@python -c "print()"
	@echo Переменные (переопределяются так: make [команда] [переменная]=[значение]):
	@echo   pkg     - имя члена workspace для check/format/lint/test/db-* (текущее: $(pkg))
	@echo   service - имя compose-сервиса для build/up_dev/up_prod (текущее: $(service))

.DEFAULT_GOAL := help

# На Windows заставляем make всегда идти через cmd.exe.
# Без этого make пытается запускать команды напрямую через CreateProcess,
# минуя PATH/PATHEXT — из-за этого .cmd/.bat-обёртки (например, mypy)
# не находятся, хотя обычные .exe (например, ruff) работают.
ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
endif
.PHONY: check format lint test test_sec_image coverage renovate \
        make_migration migrate downgrade shell logs up_dev up_prod down_dev down_prod build \
        db-revision db-upgrade db-downgrade db-current db-history \
        clean install help

# ---- Переменные по умолчанию (можно переопределить: make check path=app) ----
path       ?= .
service    ?= app
dockerfile ?= Dockerfile
message    ?= "auto"
msg        ?= "auto"

check: ## Прогнать все линтеры (ruff, mypy, ruff format --check, vulture)
	uv run ruff check $(path)
	uv run mypy --explicit-package-bases $(path)
	uv run ruff format --check $(path)
	uv run vulture ./whitelist.py $(path)

format: ## Автоформатирование кода (ruff format + ruff check --fix)
	uv run ruff format $(path)
	uv run ruff check --fix $(path)

lint: format check ## Сначала отформатировать, затем проверить (format + check)

install: ## Установить зависимости проекта (poetry/uv/pip — под ваш стек)
	pip install -r requirements.txt

test: ## Запустить тесты (pytest)
	uv run pytest

coverage: ## Запустить тесты с отчётом покрытия (make coverage service=app)
	uv run pytest --cov=$(service) --cov-report=term-missing

test_sec_image: ## Собрать и протестировать защищённый (sec) docker-образ сервиса
	docker rm $(service) || true
	docker build --file $(service)/$(dockerfile) --target sec_image --tag $(service):sec ./
	docker run --env-file .env.template --env-file $(service)/.env.template --name $(service) $(service):sec

up_dev: ## Поднять dev-профиль (только БД, приложение запускается локально)
	docker compose --profile dev up -d

up_prod: ## Поднять prod-профиль (БД + API в докере)
	docker compose --profile prod up -d --build

down_dev: ## Остановить и удалить контейнеры dev-профиля (volume с данными сохраняется)
	docker compose --profile dev down

down_prod: ## Остановить и удалить контейнеры prod-профиля (volume с данными сохраняется)
	docker compose --profile prod down

build: ## Пересобрать образы docker compose
	docker compose build $(service)

shell: ## Зайти в shell контейнера сервиса (make shell service=app)
	docker compose run --rm $(service) /bin/bash

logs: ## Смотреть логи сервиса (make logs service=app)
	docker compose logs -f $(service)

renovate: ## Запустить renovate локально через docker compose
	docker compose -f docker-compose.yml -f docker-compose.debug.yml up renovate

make_migration: ## Создать новую alembic-миграцию (make make_migration service=app message="текст")
	docker compose -f docker-compose.yml -f docker-compose.migrations.yml run --rm $(service)_migrations alembic revision --autogenerate -m "$(message)"

migrate: ## Применить все миграции (upgrade head)
	docker compose -f docker-compose.yml -f docker-compose.migrations.yml run --rm $(service)_migrations alembic upgrade head

downgrade: ## Откатить последнюю миграцию (downgrade -1)
	docker compose -f docker-compose.yml -f docker-compose.migrations.yml run --rm $(service)_migrations alembic downgrade -1

db-revision: ## Создать ревизию через autogenerate (использование: make db-revision msg="add foo")
	uv run alembic revision --autogenerate -m "$(msg)"

db-upgrade: ## Применить все непримененные миграции до head
	uv run alembic upgrade head

db-downgrade: ## Откатить последнюю миграцию на один шаг
	uv run alembic downgrade -1

db-current: ## Показать текущую ревизию БД
	uv run alembic current

db-history: ## Показать всю историю миграций
	uv run alembic history

clean: ## Удалить кэши Python и временные файлы
	python -c "import pathlib, shutil; dirs = [d for pattern in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for d in pathlib.Path('.').rglob(pattern)]; [shutil.rmtree(d, ignore_errors=True) for d in dirs]; print(f'Удалено директорий: {len(dirs)}')"

help: ## Показать список команд с описанием
	@echo Доступные команды:
	@echo   check           - Проверка кода линтерами (ruff, mypy, ruff format --check, vulture)
	@echo   format          - Автоформатирование кода (ruff format + ruff check --fix)
	@echo   lint            - format + check одной командой
	@echo   install         - Установить зависимости проекта
	@echo   test            - Запустить тесты (pytest)
	@echo   coverage        - Тесты с отчётом покрытия
	@echo   test_sec_image  - Собрать и протестировать защищённый docker-образ
	@echo   up_dev          - Поднять dev-профиль (только БД)
	@echo   up_prod         - Поднять prod-профиль (БД + API в докере)
	@echo   down_dev        - Остановить контейнеры dev-профиля
	@echo   down_prod       - Остановить контейнеры prod-профиля
	@echo   build           - Пересобрать образы docker compose
	@echo   shell           - Зайти в shell контейнера сервиса
	@echo   logs            - Смотреть логи сервиса
	@echo   renovate        - Запустить renovate локально
	@echo   make_migration  - Создать новую alembic-миграцию
	@echo   migrate         - Применить все миграции (upgrade head)
	@echo   downgrade       - Откатить последнюю миграцию
	@echo   db-revision     - Создать ревизию через autogenerate (локально, uv run alembic)
	@echo   db-upgrade      - Применить все непримененные миграции до head (локально)
	@echo   db-downgrade    - Откатить последнюю миграцию на один шаг (локально)
	@echo   db-current      - Показать текущую ревизию БД (локально)
	@echo   db-history      - Показать всю историю миграций (локально)
	@echo   clean           - Удалить кэши Python и временные файлы
	@echo.
	@echo Переменные (переопределяются так: make check path=app):
	@echo   path       - путь для линтеров/форматтера (по умолчанию: .)
	@echo   service    - имя сервиса для docker compose (по умолчанию: app)
	@echo   dockerfile - имя Dockerfile для test_sec_image (по умолчанию: Dockerfile)
	@echo   message    - текст сообщения для alembic-миграции (docker-цель make_migration)
	@echo   msg        - текст сообщения для alembic-миграции (локальная цель db-revision)

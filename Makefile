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
        make_migration migrate downgrade shell logs up down build \
        clean install help

# ---- Переменные по умолчанию (можно переопределить: make check path=app) ----
path       ?= .
service    ?= app
dockerfile ?= Dockerfile
message    ?= "auto"

check: ## Прогнать все линтеры (ruff, mypy, ruff format --check, vulture)
	ruff check $(path)
	mypy --explicit-package-bases $(path)
	ruff format --check $(path)
	vulture ./whitelist.py $(path)

format: ## Автоформатирование кода (ruff format + ruff check --fix)
	ruff format $(path)
	ruff check --fix $(path)

lint: format check ## Сначала отформатировать, затем проверить (format + check)

install: ## Установить зависимости проекта (poetry/uv/pip — под ваш стек)
	pip install -r requirements.txt

test: ## Запустить тесты сервиса в docker compose (make test service=app)
	docker compose run --rm $(service) pytest

coverage: ## Запустить тесты с отчётом покрытия
	docker compose run --rm $(service) pytest --cov=$(service) --cov-report=term-missing

test_sec_image: ## Собрать и протестировать защищённый (sec) docker-образ сервиса
	docker rm $(service) || true
	docker build --file $(service)/$(dockerfile) --target sec_image --tag $(service):sec ./
	docker run --env-file .env.template --env-file $(service)/.env.template --name $(service) $(service):sec

up: ## Поднять окружение docker compose в фоне
	docker compose up -d

down: ## Остановить и удалить контейнеры docker compose
	docker compose down

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

clean: ## Удалить кэши Python и временные файлы
	python -c "import pathlib, shutil; dirs = [d for pattern in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for d in pathlib.Path('.').rglob(pattern)]; [shutil.rmtree(d, ignore_errors=True) for d in dirs]; print(f'Удалено директорий: {len(dirs)}')"

help: ## Показать список команд с описанием
	@echo Доступные команды:
	@echo   check           - Проверка кода линтерами (ruff, mypy, ruff format --check, vulture)
	@echo   format          - Автоформатирование кода (ruff format + ruff check --fix)
	@echo   lint            - format + check одной командой
	@echo   install         - Установить зависимости проекта
	@echo   test            - Запустить тесты сервиса в docker compose
	@echo   coverage        - Тесты с отчётом покрытия
	@echo   test_sec_image  - Собрать и протестировать защищённый docker-образ
	@echo   up              - Поднять окружение docker compose в фоне
	@echo   down            - Остановить и удалить контейнеры docker compose
	@echo   build           - Пересобрать образы docker compose
	@echo   shell           - Зайти в shell контейнера сервиса
	@echo   logs            - Смотреть логи сервиса
	@echo   renovate        - Запустить renovate локально
	@echo   make_migration  - Создать новую alembic-миграцию
	@echo   migrate         - Применить все миграции (upgrade head)
	@echo   downgrade       - Откатить последнюю миграцию
	@echo   clean           - Удалить кэши Python и временные файлы
	@echo.
	@echo Переменные (переопределяются так: make check path=app):
	@echo   path       - путь для линтеров/форматтера (по умолчанию: .)
	@echo   service    - имя сервиса для docker compose (по умолчанию: app)
	@echo   dockerfile - имя Dockerfile для test_sec_image (по умолчанию: Dockerfile)
	@echo   message    - текст сообщения для alembic-миграции
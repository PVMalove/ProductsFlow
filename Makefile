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
	make_migration migrate downgrade shell logs up_dev up_prod down_dev down_prod down_dev_v down_prod_v build \
	db-revision db-upgrade db-downgrade db-current db-history db-indexes db-psql-shell db-query \
	clean install help

# ---- Переменные по умолчанию (можно переопределить: make check path=app) ----
path ?= .
service ?= app
dockerfile ?= Dockerfile
db_container ?= product-db-dev
db_user ?= admin
db_name ?= products
message ?= "auto"
msg ?= "auto"
q ?= "SELECT 1;"

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

down_dev_v: ## Остановить контейнеры dev-профиля и УДАЛИТЬ volume с данными (необратимо)
	docker compose --profile dev down -v

down_prod_v: ## Остановить контейнеры prod-профиля и УДАЛИТЬ volume с данными (необратимо)
	docker compose --profile prod down -v

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

db-indexes: ## Показать индексы PostgreSQL в dev-контейнере
	docker exec -it $(db_container) psql -U $(db_user) -d $(db_name) -c "\di"

db-psql-shell: ## Открыть интерактивный shell PostgreSQL (psql)
	docker exec -it $(db_container) psql -U $(db_user) -d $(db_name)

db-query: ## Выполнить SQL-запрос (использование: make db-query q="SELECT * FROM users;")
	docker exec -it $(db_container) psql -U $(db_user) -d $(db_name) -c $(q)

clean: ## Удалить кэши Python и временные файлы
	python -c "import pathlib, shutil; dirs = [d for pattern in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for d in pathlib.Path('.').rglob(pattern)]; [shutil.rmtree(d, ignore_errors=True) for d in dirs]; print(f'Удалено директорий: {len(dirs)}')"

help: ## Показать список команд с описанием
	@python -c "import re, sys; print('Доступные команды:'); lines = open(sys.argv[1], encoding='utf-8').readlines(); matches = [re.match(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', line) for line in lines]; [print(f'  {m.group(1):<16} - {m.group(2)}') for m in matches if m]" $(MAKEFILE_LIST)
	@python -c "print()"
	@echo Переменные (переопределяются так: make [команда] [переменная]=[значение]):
	@echo   path         - путь для линтеров/форматтера (текущее: $(path))
	@echo   service      - имя сервиса для docker compose (текущее: $(service))
	@echo   dockerfile   - имя Dockerfile для test_sec_image (текущее: $(dockerfile))
	@echo   db_container - имя контейнера PostgreSQL (текущее: $(db_container))
	@echo   db_user      - пользователь PostgreSQL (текущее: $(db_user))
	@echo   db_name      - имя базы данных (текущее: $(db_name))
	@echo   q            - SQL-запрос для make db-query (текущее: $(q))
	@echo   message      - текст alembic-миграции в докере (текущее: $(message))
	@echo   msg          - текст alembic-миграции локально (текущее: $(msg))

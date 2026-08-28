.DEFAULT_GOAL := help

# На Windows заставляем make всегда идти через cmd.exe — см. корневой Makefile
# (без этого .cmd/.bat-обёртки вроде mypy не находятся через PATH/PATHEXT).
ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
endif
.PHONY: check format lint help

# ---- Переменные по умолчанию (можно переопределить: make check pkg=identity-service) ----
pkg ?=

member_dir = $(firstword $(wildcard src/libs/$(pkg)) $(wildcard src/services/$(pkg)))

check: ## Прогнать все линтеры на члене workspace (make check pkg=<member>)
	uv run --package $(pkg) ruff check $(member_dir)
	uv run --package $(pkg) mypy --explicit-package-bases $(member_dir)
	uv run --package $(pkg) ruff format --check $(member_dir)
	uv run --package $(pkg) vulture whitelist.py $(member_dir)

format: ## Автоформатирование кода члена workspace (ruff format + ruff check --fix)
	uv run --package $(pkg) ruff format $(member_dir)
	uv run --package $(pkg) ruff check --fix $(member_dir)

lint: format check ## Сначала отформатировать, затем проверить (format + check)

help: ## Показать список команд с описанием
	@python -c "import re, sys; print('Доступные команды:'); lines = open(sys.argv[1], encoding='utf-8').readlines(); matches = [re.match(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', line) for line in lines]; [print(f'  {m.group(1):<16} - {m.group(2)}') for m in matches if m]" $(MAKEFILE_LIST)
	@python -c "print()"
	@echo Переменные (переопределяются так: make [команда] [переменная]=[значение]):
	@echo   pkg - имя члена workspace для check/format/lint (текущее: $(pkg))

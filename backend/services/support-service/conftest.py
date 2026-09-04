"""Корневой conftest для support-service — настраивает sys.path для
импортов на базе src."""

import sys
from pathlib import Path

pytest_plugins = ["test_support.postgres", "test_support.rabbitmq"]

# Добавляет src/ в sys.path, чтобы работали top-level импорты. Это нужно,
# потому что pyproject.toml перечисляет пакеты как ["src/application", ...],
# из-за чего hatchling создаёт пространство имён, где они становятся
# top-level модулями.
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

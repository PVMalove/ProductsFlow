"""Корневой conftest для identity-service — настраивает sys.path для
импортов на базе src."""

import sys
from pathlib import Path

# Добавляет src/ в sys.path, чтобы работали top-level импорты вроде
# "from core.settings". Это нужно, потому что pyproject.toml перечисляет
# пакеты как ["src/application", ...], из-за чего hatchling создаёт
# пространство имён, где они становятся top-level модулями.
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

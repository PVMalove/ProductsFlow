from infrastructure.db import audit as _audit  # noqa: F401

# Импорт выше — не для использования содержимого модуля напрямую, а чтобы
# `@event.listens_for(ProductModel, ...)`-декораторы `audit.py` (ADR 0008)
# зарегистрировались, как только кто-либо импортирует что-то из этого
# пакета (в т.ч. `product_repository.py`), без ручного импорта на вызывающей
# стороне.

# pytest требует объявлять `pytest_plugins` в top-level conftest.py, не во
# вложенном (см. test_support.postgres docstring) — интеграционные тесты
# используют общую Postgres testcontainers-фикстуру (ADR 0013, issue #369).
# Никакого RabbitMQ-плагина: order-service не публикует и не потребляет
# сообщения в этом тикете (архитектурный бриф #369, D1).
pytest_plugins = [
    "test_support.postgres",
]

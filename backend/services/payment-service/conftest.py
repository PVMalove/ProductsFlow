# pytest требует объявлять `pytest_plugins` в top-level conftest.py, не во
# вложенном (см. test_support.postgres docstring) — интеграционные тесты
# используют общую Postgres testcontainers-фикстуру (ADR 0013, issue #368).
# Никакого RabbitMQ-плагина: payment-service не публикует и не потребляет
# сообщения (архитектурный бриф #368, D1).
pytest_plugins = [
    "test_support.postgres",
]

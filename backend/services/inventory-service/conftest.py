# pytest требует объявлять `pytest_plugins` в top-level conftest.py, не во
# вложенном (см. test_support.postgres docstring) — интеграционные тесты
# используют общие Postgres/RabbitMQ testcontainers-фикстуры (ADR 0013, issue #367).
pytest_plugins = [
    "test_support.postgres",
    "test_support.rabbitmq",
]

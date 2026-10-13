# pytest требует объявлять `pytest_plugins` в top-level conftest.py, не во
# вложенном (см. test_support.postgres docstring) — интеграционные тесты
# используют общие Postgres/RabbitMQ testcontainers-фикстуры (ADR 0013,
# issue #368/#371). RabbitMQ-плагин добавлен issue #371: payment-service
# теперь потребляет payment.authorize.v1/payment.void.v1 (архитектурный
# бриф #371, D1 разворачивает #368's исходное «ноль messaging» решение).
pytest_plugins = [
    "test_support.postgres",
    "test_support.rabbitmq",
]

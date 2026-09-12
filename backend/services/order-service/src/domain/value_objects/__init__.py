"""Общий маркер приватности конструктора для value objects этого пакета
(`CartId`) — та же схема, что и `PRIVATE_MARKER` у `kernel_domain.Entity`, но
`CartId` сверяет свой `__init__` с этим локальным токеном вместо
централизованной базы (мирует `support-service`'s `domain/value_objects/__init__.py`)."""

PRIVATE_MARKER = object()

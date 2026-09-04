"""Общий маркер приватности конструктора для value objects этого пакета
(TicketId) и для `TicketMessage` (issue #252, дочерней сущности `Ticket`,
не являющейся `Entity`, без своего общего базового `__init__`) — та же
схема, что и `PRIVATE_MARKER` у `kernel_domain.Entity`, но каждый из этих
типов сверяет свой `__init__` с этим единым токеном вместо
централизованной базы."""

PRIVATE_MARKER = object()

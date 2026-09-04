"""Общий маркер приватности конструктора для value objects этого пакета
(Email, RawPassword, UserId) — та же схема, что и `PRIVATE_MARKER` у
`kernel_domain.Entity`, но у VO нет общего базового `__init__`, который
централизованно бы это обеспечивал, поэтому собственный `__init__` каждого
VO сверяется с этим единым токеном."""

PRIVATE_MARKER = object()

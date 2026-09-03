# 0033. Полная BFF-миграция identity и support

ADR 0031 ввело BFF-конверт и ограничило первый перенос catalog product commands. Теперь все бизнесовые API `identity-service` (`users`, создание пользователя и BFF-login, audit) и `support-service` (`tickets`, сообщения и audit при наличии) в текущем `/api/v1` переходят на `{\"data\": T, \"meta\": {}}` и единый error-конверт без transitional flat-ответов или `/api/v2`: кратковременная несовместимость frontend-клиентов принята ради единого контракта. JWKS, health, worker-триггеры и OAuth2 `OAuth2PasswordRequestForm` login, если его потребляет стандартный OAuth2-клиент, остаются плоскими протокольными или инфраструктурными endpoint'ами.

Роутеры не оркестрируют несколько use case и не переводят ошибки: request/query-модели строят command/query с Actor, один handler возвращает framework-independent frozen View в `Result`, а `kernel-platform` централизованно переводит Result и ожидаемые application/domain errors. В частности, detail тикета — отдельный query, возвращающий `TicketDetailView` вместе с первой страницей сообщений, а не два вызова handler из endpoint'а.

## Consequences

- Все успешные BFF read и mutation responses, включая delete с `data: null`, имеют HTTP 200 кроме созданий с HTTP 201; HTTP 204 для BFF-мутаций не используется.
- Интеграционные HTTP-тесты проверяют status и конечный BFF-конверт, а не детали handler'ов.

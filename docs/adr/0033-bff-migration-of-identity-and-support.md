# 0033. Полная BFF-миграция identity и support

ADR 0031 ввело BFF-конверт и ограничило первый перенос catalog product commands. Теперь все бизнесовые API `identity-service` (`users`, создание пользователя и BFF-login, audit) и `support-service` (`tickets`, сообщения и audit при наличии) в текущем `/api/v1` переходят на `{\"data\": T, \"meta\": {}}` и единый error-конверт без transitional flat-ответов или `/api/v2`: кратковременная несовместимость frontend-клиентов принята ради единого контракта. JWKS, health, worker-триггеры и OAuth2 `OAuth2PasswordRequestForm` login, если его потребляет стандартный OAuth2-клиент, остаются плоскими протокольными или инфраструктурными endpoint'ами.

Роутеры не оркестрируют несколько use case и не переводят ошибки: request/query-модели строят command/query с Actor, один handler возвращает framework-independent frozen View в `Result`, а `kernel-platform` централизованно переводит Result и ожидаемые application/domain errors. В частности, detail тикета — отдельный query, возвращающий `TicketDetailView` вместе с первой страницей сообщений, а не два вызова handler из endpoint'а.

Ожидаемый отказ бизнес-правила — нормальный результат use case и возвращается как `Result.err`; `match_result` поднимает структурированный `ApiError`, который обработчик `kernel-platform` сериализует в error-конверт. Сырые domain exceptions не покидают application boundary: handler преобразует их в `Result.err`. Pydantic request-модель, в том числе dependency-модель для path/query без JSON body, инкапсулирует всю транспортную валидацию и `to_command(actor)`/`to_query(actor)`; параметры URL не собираются вручную в роутере.

`/users/me` не доверяет claims как источнику View: JWT dependency строит transport-neutral `Actor(id, role)`, а `GetCurrentUserHandler` сверяет его с актуальным состоянием и возвращает `Result[UserView]`. Этот же единый Actor заменяет service-specific наборы `actor_id` и `is_admin`; View живут в service-owned `src/contracts` как frozen dataclasses и сохраняют прежние JSON-названия бизнес-полей.

`Actor` и `ActorRole` — единые framework-independent frozen contracts `kernel_platform.security`, а не service-local дубликаты. Support строит Actor по собственной event-driven user-projection, обновляемой identity событиями регистрации, (де)активации и смены роли; синхронного вызова identity на каждый BFF-запрос нет. Security dependency аутентифицирует и строит Actor, тогда как handlers авторизуют действие и возвращают `Result.err(FORBIDDEN)` при отказе.

Для self-registration инициатором audit остаётся только что созданный User: существующий обязательный `actor_user_id → users.id` не меняется. System Actor не используется для этой операции и не требует служебной строки User или специальной формы audit-записи.

Support user-projection deny-by-default: валидный JWT без локальной записи даёт `401 UNAUTHENTICATED`, а известный неактивный User — `403 FORBIDDEN`. Projection использует tombstone, а не hard delete: `user.deleted` помечает пользователя неактивным и записывает monotonic `last_applied_outbox_id`, поэтому более старые или повторно доставленные identity events не возрождают его. Frontend может кратко повторить 401 сразу после регистрации, пока асинхронная проекция догоняет событие.

## Consequences

- Все успешные BFF read и mutation responses, включая delete с `data: null`, имеют HTTP 200 кроме созданий с HTTP 201; HTTP 204 для BFF-мутаций не используется.
- `data` list-ответа содержит массив View, а pagination metadata — только корневой `meta`; у `TicketDetailView` pagination его сообщений также находится в корневом `meta`.
- `/api/v1/auth/login` остаётся плоским OAuth2 password-grant endpoint'ом для `OAuth2PasswordBearer` и Swagger UI.
- Каждый HTTP DELETE возвращает `200 {\"data\": null, \"meta\": {}}`, включая логическое удаление сообщения тикета.
- Интеграционные HTTP-тесты проверяют status и конечный BFF-конверт, а не детали handler'ов.
- Rollout атомарен по зависимостям: shared Actor, identity event contracts и support schema идут до worker/projection/authentication, а support thin endpoints — только после их готовности. Catalog получает только compatibility-refactor импортов Actor; его неохваченные BFF endpoint'ы не входят в эту миграцию.

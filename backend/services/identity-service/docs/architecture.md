# Архитектура

`api` владеет HTTP- и worker-точками входа, `application` — юзкейсами,
`domain` — бизнес-понятиями identity, `infrastructure` — персистентностью,
а `core` — локальными для сервиса политиками безопасности и конфигурации.

## Граница CQRS на уровне application

Мутации identity описаны в `application/commands/` — один модуль на операцию,
неизменяемые command-DTO и выделенный handler на каждую. `__init__.py` пакета —
публичный command-side фасад. Handler'ы зависят от доменного контракта
`IdentityUnitOfWork` (`domain/unit_of_work.py`) и порта `PasswordHasher`;
конкретные адаптеры персистентности и хеширования остаются вне application-слоя.
UoW отдаёт доменный `UserRepository`, разделяет request-scoped сессию, по
умолчанию откатывает транзакцию, если handler явно не закоммитил её на
успешном пути, и держит мутацию агрегата и её outbox-строки атомарными
(ADR 0006).

Чтения identity используют неизменяемые DTO в `application/queries/` — один
модуль на запрос и публичный фасад на уровне пакета. `GetUserQueryHandler`
принимает только `UserQueryPort`: у этого порта нет операций `add`/`save`,
поэтому query-handler не может случайно смутировать агрегат через объявленную
зависимость.

`ListUsersQueryHandler` читает курсорно-пагинированную `UserPage` администратора
через `UserListQueryPort`, используя общий контракт `kernel_platform.pagination`.
`GetUserAuditQueryHandler` использует `UserAuditQueryPort`: отсутствующий
`user_id` выбирает глобальную, offset-пагинированную `UserAuditPage`
(`page_index`/`page_size`/`total_pages`), а переданный `user_id` — полную,
непагинированную личную историю. Авторизация и различение «свой ли это `id`
вызывающего или целевой `id`, заданный администратором» — забота HTTP-границы,
не query-порта.

## Персистентность и outbox

`infrastructure/db/user_repository.py::UserRepository` маппит агрегат на
SQLAlchemy-модель `UserModel`. Каждый мутирующий метод сливает доменные
события через общую outbox-операцию `kernel-platform` явным вызовом
(не через ORM-миксин), а `infrastructure/db/unit_of_work.py::SqlIdentityUnitOfWork`
владеет единственным commit — строка пользователя и её outbox-строки поэтому
делят одну транзакцию. ORM-слушатели в `infrastructure/db/audit.py` пишут
неизменяемый audit-трейл пользователя и разрешают актора из общего
request-scoped `ContextVar` (вне HTTP — из `id` затронутого пользователя).
`SqlUserQueryRepository` и `SqlUserAuditReader` — соответствующие read-side
SQL-адаптеры, не раскрывающие хеши паролей.

## BFF-конверт и безопасность (ADR 0002, ADR 0005)

`api/endpoints/users.py` и `api/endpoints/auth.py` — тонкие: модели
`api/schemas.py` превращают запрос в command/query через
`to_command()`/`to_query()`, а `kernel_platform.http.match.match_result`/
`match_created` оборачивают application-`Result` в общий `ApiResponse`-конверт
напрямую — роутер никогда не конвертирует один тип `Result` в другой. Каждый
из `RegisterUserCommandHandler`, `ChangePasswordCommandHandler`,
`ActivateUserCommandHandler`, `DeactivateUserCommandHandler` сам строит
`contracts.user.UserView` перед тем, как вернуть `Result[UserView]` — так же,
как command-handler'ы `Product` в catalog возвращают `Result[ProductView]`
(ADR 0002).

`api/security.py::get_current_actor` декодирует bearer JWT, перечитывает
вызывающего через `UserQueryRepositoryDI` и возвращает
`kernel_platform.security.Actor` — та же перезагрузка обеспечивает проверку
`is_active` для каждого аутентифицированного identity-эндпоинта, не только для
`/users/me` (ADR 0005). `AdminActor` (`require_admin_actor` + `require_admin`
из `kernel_platform.security`) — отдельная зависимость для admin-only
маршрутов.

`GetCurrentUserHandler` (`application/queries/get_current_user.py`) —
выделенный read-путь для `/users/me`: он заново перечитывает строку
вызывающего и возвращает `contracts.user.UserView`, поэтому ответ никогда не
доверяет claim'ам JWT напрямую. `GetUserAuditQueryHandler` принимает и
`UserAuditQueryPort`, и `UserQueryPort`, возвращает `Result` и сам завершает
запрос ошибкой `NOT_FOUND` для неизвестного целевого пользователя, не
перекладывая эту проверку на роутер.

`POST /api/v1/auth/login` сохраняет плоский OAuth2 password-grant ответ —
ADR 0002 явно исключает его из BFF-конверта, чтобы `OAuth2PasswordBearer` и
Swagger UI продолжали работать без изменений.

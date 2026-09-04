# 0007. Identity: доменная модель и бизнес-правила

**Статус:** Accepted. Общий канон слоёв/CQRS/UoW/GUID — [ADR 0006](0006-service-internal-architecture-baseline.md).

`identity-service` владеет единственным агрегатом — `User` — и является единственным поставщиком истины о личности (id, роль, активность) для остальной системы.

## Жизненный цикл `User`

- Создаётся только через `User.create(...) -> Result[User]` (валидация email/пароля) — self-registration. Инициатором audit-записи саморегистрации остаётся сам только что созданный `User` (`actor_user_id → users.id`); служебный System Actor для этой операции не заводится.
- **Деактивация** (`is_active=False`) — обратимое административное действие, отличное от удаления; переключается только `ADMIN`.
- **Самостоятельное удаление** — необратимое, инициируется самим пользователем через `DELETE /api/v1/users/me`. `User` не удаляется физически: заменяется анонимизированным **надгробием** (Tombstone) с терминальным `is_deleted=True` — email/пароль стёрты, аутентификация невозможна. Tombstone нельзя реактивировать: прежний bearer token его владельца получает `403 FORBIDDEN`, а не тихий anonymous fallback.
- Смена роли (`role_changed`) — административное действие, отдельное от активности.

Событийная сторона этих переходов (публикация `user.*.v1`, включая `user.deleted.v1`) — [ADR 0010](0010-identity-service-event-integration.md).

## Audit trail через ORM event listeners

Каждая мутация `User` (регистрация/смена пароля/(де)активация/смена роли/удаление) попадает в `UserAuditLog` вместе с Actor (`actor_user_id`). Записи вставляются не явным вызовом в repository/handler, а SQLAlchemy ORM event listeners (`@event.listens_for(UserModel, "after_insert"/"before_update")`, `infrastructure/db/audit.py`) — гарантирует, что ни один путь мутации, включая будущий, не забудет залогировать действие.

- Actor — неявное состояние: `observability.context.actor_id_var` (см. [ADR 0005](0005-security-auth-actor-contract.md)), а не параметр функции.
- **Одно доменное событие — одна audit-строка.** `User.delete()` в одном вызове меняет `email`/`password_hash`/`is_active`/`is_deleted` разом; listener явно проверяет `is_deleted`-переход первым и возвращается с единой записью `DELETED`, чтобы не задвоить её описанием «смена пароля» + «деактивация».
- `UserAuditLog.user_id`/`actor_user_id` — с `ForeignKey` на `users.id`: `User`-строка при удалении не исчезает физически (остаётся Tombstone), внешний ключ не мешает вставке audit-записи при `before_update`.
- Действия: `REGISTERED`, `PASSWORD_CHANGED`, `ACTIVATED`, `DEACTIVATED`, `ROLE_CHANGED`, `DELETED`.

## Пароль

Хеширование пароля — стейтлес-сервис (`PasswordHasher`), не порт персистентности агрегата.

## Consequences

- `identity-service` — единственный сервис, который меняет `is_active`/`role` авторитетно; catalog и support только читают следствия этих мутаций через события ([ADR 0010](0010-identity-service-event-integration.md)–[0012](0012-support-service-event-integration.md)).
- Tombstone — состояние `User`, не отдельная сущность: код, читающий `User`, обязан проверять `is_deleted` так же, как проверяет `is_active`.

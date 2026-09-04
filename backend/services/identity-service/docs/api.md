# API

Сервис отдаёт RS256 JWKS на `GET /.well-known/jwks.json` (`api/endpoints/jwks.py`)
и identity-контракт под префиксом `/api/v1`.

## Аутентификация (`api/endpoints/auth.py`)

- `POST /api/v1/auth/register` принимает `{email, password}` и возвращает
  созданного пользователя с кодом `201`.
- `POST /api/v1/auth/login` принимает OAuth2-форму (`username` — email,
  `password`) и возвращает bearer access-токен с UUID-идентификатором
  агрегата в `sub`. Это единственный эндпоинт, который остаётся плоским
  протокольным ответом ради `OAuth2PasswordBearer`/Swagger UI и не обёрнут
  в BFF-конверт (ADR 0002).

## Пользователи (`api/endpoints/users.py`)

`GET /api/v1/users/me` и `PATCH /api/v1/users/me/password` доступны текущему
активному пользователю. Каждый bearer-запрос перечитывает учётную запись из
Postgres, поэтому деактивация вступает в силу немедленно даже для уже
выданных токенов (ADR 0005).

`DELETE /api/v1/users/me` — необратимое самостоятельное удаление: учётная
запись заменяется анонимизированным tombstone, а не удаляется физически
(ADR 0007).

Администраторам доступны:

- `GET /api/v1/users/` — курсорная пагинация (`limit`, `after`, `before`);
- `PATCH /api/v1/users/{user_id}/activate` и `/deactivate`;
- `GET /api/v1/users/audit?page_index=&page_size=` — глобальная,
  offset-пагинированная audit-лента по всем пользователям;
- `GET /api/v1/users/{user_id}/audit` — audit-история конкретного
  пользователя.

Текущий пользователь может прочитать собственную историю на
`GET /api/v1/users/me/audit`. Audit-записи неизменяемы и пишутся ORM-слушателями
в той же транзакции, что и сама мутация пользователя.

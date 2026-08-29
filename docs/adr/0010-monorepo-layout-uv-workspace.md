# 0010. Раскладка монорепо для распила на микросервисы

> **Superseded частично, в части общего `uv`-workspace/`.venv`, решением [ADR 0020](0020-per-package-environments-supersedes-0010.md)**: единый workspace заменён пятью независимыми пакетами, каждый со своим `uv.lock`/окружением, под плоским `backend/libs/*`/`backend/services/*` без внешнего `src/`. Текст ниже сохранён как есть — не переписывается задним числом.

Распил монолита на `identity`/`catalog`/`support` (TD-01, Фазы 0–6) требует решить, где физически живёт новый код и что происходит с существующим `app/`. Код бэкенда переезжает в `backend/`, который становится корнем `uv` workspace; внутри `backend/src/` лежат `libs/common-kernel` и три `services/*-service`, каждый — самостоятельный член workspace со своим `pyproject.toml`, внутренним `src/<pkg>/`, собственными `alembic/`, `tests/` и `Dockerfile`. Монолит при этом не переносится и не переписывается: `app/` вместе с корневыми `alembic/`, `tests/` и `pyproject.toml` остаётся на месте как несобираемый исходник-справка, выводится из CI в Фазе 0 и удаляется по доменам — `support` после Фазы 5, `identity` и `catalog` только вместе после Фазы 4, поскольку сцеплены в общих `models.py`, `repository.py`, `schemas.py`, `security.py` и `audit.py`.

```
ProductsFlow/
  pyproject.toml                    монолит; выведен из CI в Ф0, не собирается
  Makefile                          старый, доживает вместе с app/
  app/  alembic/  tests/            только чтение; удаляются по доменам
  Dockerfile                        умирает вместе с app/
  client/                           заморожен до Фазы 7b
  docs/

  backend/                          корень uv workspace
    pyproject.toml
    Makefile                        новый, мультисервисный
    whitelist.py  .env  .env.example
    docker-compose.yml              база
    docker-compose.dev.yml          override
    docker-compose.prod.yml         override
    docker-compose.migrations.yml   место под one-off миграции
    infra/
    src/
      libs/common-kernel/           pyproject.toml + src/common_kernel/
      services/identity-service/    pyproject.toml + src/identity_service/
                                    + alembic/ + tests/ + Dockerfile
      services/catalog-service/     то же
      services/support-service/     то же
```

Остальные части решения:

- **Окружение.** Вся бэкенд-инфраструктура — под `backend/`. Один `.env` с префиксами по сервисам (`IDENTITY_DATABASE_URL` и т. п.); compose раздаёт каждому сервису его подмножество через `environment:`.
- **compose.** База плюс override для `dev`/`prod`; каждый сервис объявлен ровно один раз.
- **CI.** Матрица: отдельная джоба на `common-kernel` и на каждый сервис. `app/` из CI исключён.
- **Воркер.** Outbox-паблишер и консьюмеры — вторые точки входа того же пакета сервиса: один образ, разные `CMD` в compose.
- **Makefile.** Новая переменная `pkg` поверх `uv run --package` адресует член workspace; существующая `service` сохраняет прежний смысл имени compose-сервиса.

## Considered Options

- **Плоский src-layout** — один `pyproject.toml`, сервисы как пакеты внутри `backend/src/`. Отклонено: без отдельных `pyproject.toml` нет ни раздельных зависимостей, ни раздельных образов, ни раздельных миграционных историй. Это модульный монолит, а не микросервисы, — прямо противоположно тому, ради чего затевается распил.
- **Корень workspace в корне репозитория** — объявить членов как `backend/src/...`, оставив `pyproject.toml` наверху. Отклонено: репозиторий шире бэкенда (`client/`, `docs/`), и Python-оснастка в корне рядом со статическим фронтендом смазывает границу. Экономия на правках путей мнимая — CI и Makefile переписываются в любом случае.
- **Перенос `app/` в `backend/` временным членом workspace** — дал бы один `.venv` и один Makefile на переходный период. Отклонено: тратит PR Фазы 0 на правку импортов, путей `alembic` и `Dockerfile` в коде, который через несколько фаз будет удалён.
- **Сохранение `app/` в CI до Фазы 5** — держать монолит зелёным как исполняемый эталон. Отклонено: эталоном он не работает — тесты разносятся по сервисам и адаптируются там, а не замораживаются как golden-набор, так что расходовать на монолит CI-время незачем.
- **Профили `dev`/`prod` с дублированием сервисов, как сейчас** — отклонено: при трёх сервисах, трёх воркерах, трёх БД, RabbitMQ и MinIO дублирование даёт около двадцати определений в одном файле. Цена отказа — dev- и prod-стеки больше не поднимаются одновременно; сценария, где это нужно, нет.
- **Отдельный член workspace на каждый воркер** (`services/identity-worker/`) — отклонено: удваивает число членов с трёх до шести и вынуждает экспортировать внутренности сервиса наружу ради его же воркера.

## Consequences

- Корень репозитория остаётся Python-проектом до конца Фазы 5: два `pyproject.toml`, два `.venv`, два Makefile сосуществуют. Это временно и принято осознанно.
- `app/` перестаёт быть запускаемым уже в Фазе 0. Сверка «поведение сохранено 1-в-1», которую требуют DoD Фаз 1–5, опирается на чтение исходника, `CONTEXT.md` и ADR 0001–0009, а не на прогон старого кода.
- Корневой `Dockerfile` становится мёртвым сразу после вывода `app/` из CI и удаляется вместе с монолитом.
- `CLAUDE.md` расходится с реальностью и правится в Фазе 0: описывает `app/router/` в единственном числе, тогда как в коде `app/routers/` плюс отдельный пакет `app/support/`, и документирует `make make_migration`/`make migrate` как рабочий путь, хотя `docker-compose.migrations.yml` в репозитории отсутствует.
- Шесть целей Makefile сломаны ещё до начала работ: `make_migration`, `migrate`, `downgrade` ссылаются на несуществующий `docker-compose.migrations.yml`, `renovate` — на `docker-compose.debug.yml`, `install` — на `requirements.txt`, `test_sec_image` — на `app/Dockerfile`. Новый `backend/Makefile` пишется с нуля; старый доживает вместе с монолитом и не чинится.
- Появление `docker-compose.migrations.yml` даёт готовое место для выноса `alembic upgrade` из `lifespan` — решение по механизму принимается отдельно (техдолг №5 TD).

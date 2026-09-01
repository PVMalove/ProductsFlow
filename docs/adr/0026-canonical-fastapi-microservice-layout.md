# 0026. Каноническая структура каждого FastAPI-микросервиса

**Статус:** Accepted\
**Дата:** 2026-09-01\
**Дополняет:** [ADR 0025](0025-application-layer-ports-and-local-cqrs.md)\
**Связанные issues:** #156, #163

## Контекст

В `backend/services/*` исторически сосуществуют разные раскладки: исходный
код лежит в `src/<package>/`, HTTP-адаптер называется `api/`, а `core`/`common`,
performance, `k8s`, service-local CI и `scripts` не имеют единого места. Это
затрудняет навигацию между сервисами и не выражает выбранную Clean Architecture
границу в физическом дереве.

Пользователь выбрал структуру проекта из
[FastAPI Microservice Template](https://github.com/onlythompson/fastapi-microservice-template):
`src/application`, `src/domain/events`, `src/infrastructure`,
`src/presentation`, `src/core`, `src/common`, а также `tests/performance`,
`k8s`, `docs`, `ci` и `scripts` в корне микросервиса.

## Решение

Каждый независимо разворачиваемый сервис в `backend/services/<service>/` обязан
иметь следующую структуру. Это шаблон **сервиса**, а не замена существующей
мультисервисной раскладки `backend/services/`.

```text
<service>/
  src/
    application/
    domain/
      events/
    infrastructure/
    presentation/
    core/
      feature_flags.py
      resilience.py
      secrets.py
      rate_limiter.py
    common/
  tests/
    unit/
    integration/
    e2e/
    performance/
      locustfile.py
  k8s/
    deployment.yaml
    service.yaml
    ingress.yaml
  docs/
    api.md
    architecture.md
    adr/
  ci/
    Jenkinsfile
    github-actions-workflow.yml
  scripts/
    secret_rotation.sh
  .env
  .env.example
  .gitignore
  docker-compose.yml
  Dockerfile
  pyproject.toml
  README.md
  requirements.txt
```

`presentation` заменяет прежнее имя `api`: в нём находятся FastAPI-роутеры,
HTTP-схемы, AMQP-консьюмеры и composition root для DI. `core` — только
кросс-срезная политика данного сервиса; `common` — его локальные простые
утилиты. Общий код между сервисами по-прежнему проходит admission-правило
ADR 0013 и живёт только в `backend/libs/`.

Это целевое состояние после выполнения механической миграции из issue #163.
До её завершения действуют текущие legacy-пути и репозиторный CI; service-local
`ci/` и остальные элементы дерева не подменяют общий GitHub Actions-процесс.

`application` владеет use case и портами, `domain` — предметной моделью,
`infrastructure` — адаптерами, согласно ADR 0025. Физическая структура не
отменяет правило направлений зависимостей.

## Рассмотренные варианты

- **Оставить `src/<package>/api` и документировать его как второй допустимый
  стиль.** Отклонён: параллельные названия одного слоя создают постоянную цену
  поиска и превращают правила архитектуры в предпочтение, а не контракт.
- **Собрать все сервисы под одним `backend/src/`.** Отклонён: разрушает
  изоляцию пакетов, их окружений, Docker-образов и миграций из
  ADR 0020.
- **Копировать из референса Kafka, Redis, Kubernetes-реализацию и CI-пайплайны
  вместе с деревом.** Отклонён: структура не доказывает необходимость этих
  технологий. Их внедрение требует отдельного ADR.

## Последствия

- Появляется один целевой путь для переноса существующего кода и для новых
  сервисов; миграцию выполняет issue #163 до предметных рефакторингов #157–#160.
- Абсолютные импорты, `pyproject.toml`, точки входа Docker, Alembic и тесты
  меняются согласованно в пределах каждого сервиса; миграция не меняет HTTP,
  AMQP или persistence-контракт.
- Репозиторная документация `docs/` остаётся местом межсервисных ADR; сервисные
  документы дублируют только информацию, относящуюся к одному сервису.

## Пересмотр

Пересмотреть только при появлении нового типа независимо разворачиваемого
компонента, для которого доказано, что эта структура не применима. Обычная
потребность в новой библиотеке или технологии не является поводом добавлять
ещё один каталог верхнего уровня.

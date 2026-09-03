# 0034. Unit of Work: контракт транзакции для command handler'ов

**Статус:** Accepted\
**Дата:** 2026-09-03\
**Supersedes:** пример `Transaction`/`commit_with_outbox()` в [ADR 0028](0028-cqrs-baseline-and-architecture-check.md) (остальной текст 0028 не пересматривается, см. ниже)\
**Связанные issues:** #243 (epic), #244 (этот ADR), #245 (kernel-platform + support-service), #246 (catalog-service), #247 (identity-service)

## Контекст

В backend нет абстракции транзакции. `commit()` вызывает сам репозиторий —
приватный `_commit()`/инлайновый `session.commit()` внутри
`product_repository.py` (catalog-service), `user_repository.py`
(identity-service) и репозитория тикетов (support-service), причём
непоследовательно: часть мутирующих методов одного и того же репозитория
коммитит отдельно (например, у catalog `delete`, `upsert_product_image`,
`delete_product_image` коммитят по отдельности, каждый своим вызовом). Если
command handler вызывает 2+ мутирующих метода репозитория, это уже сейчас не
атомарно: при ошибке между вызовами первая мутация остаётся закоммиченной, а
вторая — нет.

Дополнительно, [ADR 0028](0028-cqrs-baseline-and-architecture-check.md)
содержит пример command handler'а, использующего порт `Transaction` с методом
`commit_with_outbox(events)`. Ни `Transaction`, ни `commit_with_outbox()` не
реализованы ни в одном сервисе — фактический код коммитит внутри репозитория,
а `drain_events_to_outbox` (ADR 0029) вызывается отдельно, не через
транзакционный порт. Пример в 0028 — аспирационный и разошёлся с кодом;
архитектурная документация противоречит реальности.

## Решение

`kernel-platform` получает generic `UnitOfWork` — **structural `Protocol`, не
`ABC`** (тот же стиль, что и у существующих repository-портов, ADR 0027),
объявляющий только жизненный цикл транзакции:

```python
class UnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

Протокол не знает ни об одном конкретном репозитории — это инфраструктурная
забота про сессию/транзакцию. Живёт рядом с `outbox/drain.py` в
`kernel-platform`, не в `kernel-domain` — тот же прецедент, что ADR 0027 уже
использовало для repository-контрактов. Допускается общий конкретный базовый
класс в `kernel-platform`, реализующий повторяющуюся бухгалтерию (reuse
переданной сессии, rollback по умолчанию, никогда не закрывать сессию), чтобы
три сервиса не дублировали её по отдельности.

Каждый сервис расширяет generic-контракт собственным Protocol с
атрибутами-репозиториями этого сервиса, например:

```python
class SupportUnitOfWork(UnitOfWork, Protocol):
    tickets: TicketRepository
```

Аналогично `CatalogUnitOfWork`/`IdentityUnitOfWork` — набор атрибутов
соответствует репозиториям, которые сегодня получают command handler'ы этого
сервиса. Конкретная реализация **переиспользует уже существующую
request-scoped `AsyncSession`**, полученную параметром конструктора — не
создаёт свою через `session_factory()` — и инстанцирует репозитории сервиса
поверх той же сессии. `UnitOfWork.__aexit__` не закрывает сессию: её
жизненный цикл остаётся за существующим teardown в `get_db_session`.

**Rollback по умолчанию:** если `commit()` не был вызван явно — ни через
исключение, ни через штатный возврат без коммита — транзакция откатывается
при выходе из `async with self.uow:`. Command handler оборачивает тело в
`async with self.uow:` и явно вызывает `await self.uow.commit()` только на
успешном пути; ранний `Result.error(...)`-возврат или исключение этот вызов
пропускают, и транзакция откатывается.

Репозитории перестают сами коммитить: из всех мутирующих методов убирается
`session.commit()`/`_commit()`. **Явный вызов
`drain_events_to_outbox(session, entity)` (ADR 0029) сохраняется на прежнем
месте — в точке мутации** — не переезжает в `uow.commit()`. ADR 0021 не
пересматривается: drain остаётся explicit-вызовом, не автоматическим сбором
событий из `session.new`/`session.dirty`.

Раскатка — тремя последовательными PR в интеграционную ветку
`integration/unit-of-work`: kernel-platform + support-service (#245,
наименьший риск — меньше всего handler'ов, уже есть прецедент про
outbox-through-repository), затем catalog-service (#246), затем
identity-service (#247).

## Considered Options

- **`ABC` вместо `Protocol`** — отклонено: repository-порты в этой кодовой
  базе уже объявлены как structural `Protocol` (ADR 0027); `UnitOfWork` — тот
  же тип контракта (граница между application и infrastructure), и `ABC`
  ввёл бы второй, непоследовательный стиль объявления портов без причины.
- **Единый кросс-сервисный UoW поверх трёх БД** — отклонено: у каждого
  сервиса своя БД (ADR 0010) и своя `AsyncSession`; кросс-сервисная
  транзакция потребовала бы распределённого coordinator'а (2PC или saga),
  которого этот epic прямо не рассматривает (см. Out of Scope #243). Контракт
  остаётся per-service; координация между identity/catalog/support вне рамок
  этого решения.
- **UoW с собственным `session_factory()`** — отклонено: сервисы уже
  используют request-scoped `AsyncSession` через существующий DI
  (`get_db_session`); UoW, создающий свою сессию, завёл бы вторую параллельную
  сессию на тот же request и сломал бы транзакционную границу, которую уже
  задаёт FastAPI dependency lifecycle. Приём уже существующей сессии
  параметром сохраняет один источник истины.
- **Ревизия ADR 0021 в сторону автоматического сбора событий через
  `session.new`/`session.dirty`** — отклонено: ADR 0021 сознательно выбрало
  explicit drain в точке мутации; автоматический сбор через SQLAlchemy
  identity map неявно связывает outbox-запись с ORM internals и не был
  запрошен этим epic'ом (Out of Scope #243 явно исключает пересмотр 0021).
  `UnitOfWork` добавляет транзакционную границу поверх существующего
  explicit-контракта, не заменяет его.
- **Commit по умолчанию вместо rollback по умолчанию** — отклонено:
  commit-по-умолчанию превращает забытый вызов `uow.commit()` в тихо
  персистентную частичную мутацию — ровно тот класс бага, который UoW должен
  устранить. Rollback-по-умолчанию делает «забыли закоммитить» безопасным по
  умолчанию: максимум потерянная (не персистентная) валидная мутация,
  никогда — незавершённая частичная.

## Отношение к существующим ADR

- **ADR 0028**: только пример `Transaction`/`commit_with_outbox()` помечен
  superseded (см. заметку в самом файле); остальной текст не пересматривается.
- **`backend/services/support-service/docs/adr/0002-outbox-through-repository.md`**:
  получает точечную заметку об устаревании формулировки «репозиторий сам
  коммитит транзакцию» (см. заметку в самом файле).
- **ADR 0027** (repository-контракт принадлежит domain) — не пересматривается.
  `UnitOfWork` не заменяет repository-порты, а добавляет транзакционную
  границу вокруг них; per-service Protocol (`SupportUnitOfWork` и т.д.) лишь
  агрегирует уже существующие repository-контракты атрибутами.
- **ADR 0029** (generic drain-в-outbox) и **ADR 0021** (catalog outbox write
  mechanism) — не пересматриваются, см. Решение и Considered Options выше.

## Consequences

- Command handler получает один параметр `uow: <Service>UnitOfWork` вместо
  отдельных мутирующих репозиториев; read-only cross-cutting порты
  (`IdentityGateway`, `OwnerReadModel` и т.п.) остаются отдельными
  параметрами конструктора.
- Handler, вызывающий 2+ мутирующих метода репозитория, становится атомарным:
  одна транзакция, один `uow.commit()` на успешном пути.
- `backend/libs/test-support` получает общий `FakeUnitOfWork` (async context
  manager, флаги `committed`/`rolled_back`, без реальной БД); существующие
  unit-тесты command handler'ов переводятся на конструирование через fake UoW
  вместо прямой инъекции fake-репозитория.
- Существующие SAVEPOINT-фикстуры integration-тестов (`db_session`,
  `dependency_overrides[get_db_session]`) не меняются — UoW работает поверх
  той же переопределённой сессии.
- Query handlers (13 штук) не затрагиваются — продолжают получать
  репозитории/read-модели напрямую через `Depends`.
- Раскатка на три сервиса идёт самостоятельными PR (#245, #246, #247), каждый
  независимо ревьюабелен и мёржабелен; до завершения всех трёх часть
  сервисов временно коммитит через `UnitOfWork`, часть — по-прежнему через
  репозиторий (переходное состояние, не одновременный big-bang).

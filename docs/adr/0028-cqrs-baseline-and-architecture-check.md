# ADR 0028: CQRS baseline and architecture check

## Статус

Принято. Baseline вводится для активного кода в `backend/`; frozen monolith
`app/` в область действия не входит.

## Контекст

Сервисы уже изолированы по bounded context и слоям, но application-модули
местами объединяют операции записи и чтения. Без общего контракта следующая
миграция может закрепить смешанные use case-фасады и незаметно направить
query-side через command-side.

## Решение

### Термины и правила

- **Command** — неизменяемый входной DTO операции, которая может изменить
  состояние, породить доменное событие или отправить сообщение через outbox.
- **Query** — неизменяемый входной DTO чтения. Query не меняет состояние, не
  публикует события и не выполняет побочных эффектов.
- **Handler** — application-объект с одной ответственностью. Он получает порты
  конструктором и не знает о FastAPI, SQLAlchemy, RabbitMQ или S3.
- **Command-side port** — application/domain Protocol для агрегатной записи,
  транзакции и outbox. **Query-side port** — Protocol для чтения или
  специализированной read model; он не предоставляет mutation-методы.
- **DTO** — транспортно-нейтральные данные входа/выхода application boundary.
  HTTP-схемы остаются в адаптере и не становятся доменными сущностями.
- **Направление зависимостей:** adapter → application → domain; infrastructure
  реализует порты и подключается в composition root. Domain/application не
  импортируют infrastructure, FastAPI или SQLAlchemy.
- **Транзакция:** command-handler выполняет mutation и запись transactional
  outbox атомарно в одной транзакции репозитория. Query-handler использует
  read model/projection и не открывает command-side путь.

Новый код использует layout `application/commands/` и
`application/queries/` с одним bounded-context модулем на связанную группу
сценариев и отдельными handler-типами. Оба пакета обязаны иметь
`__init__.py`, который является фасадом публичных типов; реализации живут в
отдельных модулях по операции, например:

```text
application/commands/
├── __init__.py
├── register_user.py
├── login.py
├── change_password.py
└── deactivate_user.py
application/queries/
├── __init__.py
└── get_user.py
```

Такой layout сохраняет небольшой внешний интерфейс пакетов, повышает locality
изменений каждой команды и запроса и не превращает один файл в shallow-модуль
с растущим списком несвязанных сценариев. Старые пути импорта могут временно
оставаться compatibility adapters, делегирующими в пакет. Общие
`ICommand`/`IQuery`, глобальный dispatcher и event sourcing не требуются.

### Пример команды

```python
@dataclass(frozen=True)
class DeactivateUserCommand:
    user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, users: UserRepository, tx: Transaction) -> None:
        self._users = users
        self._tx = tx

    def handle(self, command: DeactivateUserCommand) -> Result[User]:
        user = self._users.get(command.user_id)
        if user is None:
            return Result.failure(USER_NOT_FOUND)
        user.deactivate()
        self._tx.commit_with_outbox(user.pull_domain_events())
        return Result.success(user)
```

### Пример запроса

```python
@dataclass(frozen=True)
class ListTicketsQuery:
    viewer_id: UserId | None
    limit: int


class ListTicketsQueryHandler:
    def __init__(self, tickets: TicketReadModel) -> None:
        self._tickets = tickets

    async def handle(self, query: ListTicketsQuery) -> TicketPage:
        return await self._tickets.list_visible(query.viewer_id, query.limit)
```

## Аудит текущего состояния

Проверены `identity-service`, `catalog-service`, `support-service`, а также
`kernel-domain`, `kernel-platform`, `observability` и `test-support`.

| Область | Найдено | Решение в baseline |
| --- | --- | --- |
| `identity-service/src/application` | команды и запросы identity выделены в пакеты `commands/` и `queries/`, по одному модулю на операцию; старые command-файлы оставлены compatibility adapters | считать identity эталонным примером пакетного CQRS layout |
| `catalog-service/src/application/product_use_cases.py` | `Create/Update/Activate/Deactivate/Delete` смешаны с `Get/List/GetAudit` | migration finding; разделить в #187 |
| `catalog-service/src/application/product_image_use_cases.py` | `GetProductImage` смешан с `UpsertProductImage/DeleteProductImage` | migration finding; разделить в #187 |
| `support-service/src/application/ticket_use_cases.py` | `CreateTicket` смешан с `GetTicket/ListTickets/ListAdminTickets` | migration finding; разделить в #188 |
| shared libraries | прикладных use case-модулей нет | нарушений CQRS не найдено |
| все `domain/` и `application/` | blocking imports `infrastructure`, FastAPI или SQLAlchemy не обнаружены | enforced автоматически |

Аудит воспроизводим: `python backend/scripts/check_architecture.py` печатает
`MIGRATION` findings и blocking `ERROR` findings. `--strict` возвращает ненулевой
код только для blocking dependency-direction нарушений, поэтому baseline можно
подключить к CI до завершения поэтапной миграции. Новые violations не должны
получать compatibility-исключения без отдельной ADR.

## Compatibility adapters

`src/api` сохраняется как внешний adapter до завершения перехода к
`presentation/`; его composition root может собрать конкретные infrastructure
реализации и передать их через application ports. Смешанный use-case-фасад также
может временно делегировать в новые command/query handlers. Такие адаптеры не
добавляют бизнес-правил, помечаются в аудите и удаляются после миграции сервиса.

## Последствия

Команды получают явную транзакционную границу и сохраняют текущие security,
visibility и outbox-контракты. Запросы можно оптимизировать read models без
изменения агрегатов. На время миграции архитектурный check сообщает известные
несмешанные violations отдельно от blocking layer violations; issues #186–#189
закрывают migration findings по bounded context и enforcement.

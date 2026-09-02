# ADR 0028: CQRS baseline and architecture check

## Статус

Принято и применяется. Enforcement действует для активного кода в `backend`;
frozen monolith `app/` в область действия не входит.

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
- **Граница CQRS:** модули `application/commands/` и
  `application/queries/` не импортируют друг друга. Повторное использование
  логики оформляется через domain или нейтральный application helper.
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
| `identity-service/src/application` | команды и запросы identity выделены в пакеты `commands/` и `queries/`, по одному модулю на операцию; старые пути оставлены только как command-only compatibility adapters | пакетный CQRS layout — эталон для новых сценариев |
| `catalog-service/src/application/commands/` and `queries/` | product CRUD, visibility, pagination, audit, and image operations имеют immutable DTO и dedicated handler на операцию; смешанные фасады удалены | миграция завершена в #187 |
| `support-service/src/application/commands/` and `queries/` | ticket creation, ticket visibility, ticket lists and message pagination используют отдельные command/query DTO и handlers; смешанный фасад удалён | миграция завершена в #188 |
| shared libraries | прикладных use case-модулей нет | нарушений CQRS не найдено |
| все `domain/` и `application/` | blocking imports `infrastructure`, FastAPI или SQLAlchemy не обнаружены; mixed command/query modules отсутствуют | enforced автоматически |

Аудит воспроизводим: `python backend/scripts/check_architecture.py` печатает
blocking `ERROR` findings. `--strict` возвращает ненулевой код при любом
нарушении направления зависимостей или CQRS-разделения, включая cross-side
imports и mixed-use-case modules. Тот же gate запускается в CI и через
`make -C backend architecture-check`. Новые violations не должны
получать compatibility-исключения без отдельной ADR.

## Compatibility adapters

`src/api` остаётся внешним transport adapter: его composition root может собрать
конкретные infrastructure-реализации и передать их через application ports.
Смешанные use-case-фасады не допускаются и удалены в catalog/support. Старые
identity-пути сохранены только как явно названные command-only re-export
adapters, чтобы не менять существующие import contracts; они не содержат
бизнес-логики и не могут быть шаблоном для нового кода.

## Последствия

Команды получают явную транзакционную границу и сохраняют текущие security,
visibility и outbox-контракты. Запросы можно оптимизировать read models без
изменения агрегатов. Архитектурный check блокирует новые mixed-use-case и layer
violations, а миграции identity, catalog и support не оставляют таких findings.
Issue #189 закрывает enforcement по bounded context.

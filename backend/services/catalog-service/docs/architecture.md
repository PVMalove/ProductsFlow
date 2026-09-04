# Архитектура

`api` владеет HTTP-точками входа, схемами и корнем композиции FastAPI.
HTTP-обработчики товара (`api/endpoints/products.py`,
`api/endpoints/product_images.py`) только транслируют запрос и ответ.
Команды товара лежат по одной на операцию в `src/application/commands/`,
запросы — по одному на операцию в `src/application/queries/`; у каждой
операции — неизменяемый DTO и выделенный handler с точкой входа `handle()`.
Вызывающий код использует публичные фасады пакетов команд и запросов
напрямую.

Application-код зависит от явных command/query-портов доступа к `Product` и
от портов read-модели владельца, поиска identity, хранилища картинок и
audit-чтений. Command-handler'ы владеют мутациями, query-handler'ы — видимостью,
пагинацией, audit'ом и чтением картинок.

Command-handler'ы загружают агрегат через command-порт `Product`, когда им
нужно авторизовать или провалидировать мутацию; они не приводят репозиторий к
query-порту — query-порты зарезервированы за query-handler'ами.
`ProductVisibilityPolicy` (ADR 0008) остаётся в `domain`. SQLAlchemy-реализации
собираются только в `api/dependencies.py`, а `api` маппит application-ошибки
на неизменный HTTP-статус и контракт ответа.

## Второй процесс: воркер (ADR 0011)

Тот же `api`-слой владеет `api/worker.py` — вторым процессом образа catalog
(наравне с identity-worker, ADR 0010). Он объявляет топологию
`catalog.user-events` через `kernel-platform`, потребляет четыре
поддерживаемых события `user.*.v1` (включая разреженные payload'ы текущей
доменной модели identity) и применяет каждый снепшот владельца через
inbox/version-guard'ы `owner_read_model` (ADR 0011): не read-then-write —
конкурентные писатели (событийный консьюмер и синхронный добор при холодном
промахе) разрешаются атомарным upsert с проверкой версии по
`last_applied_outbox_id`.

## Изображения товара (ADR 0002, ADR 0003)

`api/endpoints/product_images.py` устроен так же, как `products.py`: модели
запроса `api/schemas.py` (`ProductImageGetRequest`, `ProductImageUploadRequest`,
`ProductImageDeleteRequest`) владеют всей транспортной валидацией — включая
проверку content-type и размера в `ProductImageUploadRequest.to_command()`,
которая теперь бросает `ProductImageUnsupportedMediaTypeError`/
`ProductImageTooLargeError` (`application/errors.py`) вместо сырого
`HTTPException` в роутере. Три обработчика картинки возвращают
`Result[ProductImageView]`/`Result[ProductImageMutation]`/`Result[None]`,
разворачиваемые `match_result` точно так же, как `get_product`/`activate_product`.
`GetProductImageQueryHandler` и оба handler'а мутации сохраняют существующие
короткие пути `raise ProductNotFoundError`/`ProductImageNotFoundError` для
случаев «не найден»/«не виден» — та же гибридная форма (raise для отсутствия,
`Result` для успеха), что уже использует `get_product.py`. `DELETE` возвращает
`200` с `data: null`.

Эндпоинт загрузки вызывает `UpsertProductImageCommandHandler`, а затем
`GetProductImageQueryHandler` — два отдельных вызова handler'а, а не
роутер-оркестрацию, которую ADR 0002 запрещает в остальных местах: это
исключение оправдано тем, что `ProductImageMutation` намеренно несёт только
`replaced: bool` и никогда query-side View (command/query-разделение, которое
кодовая база явно тестирует). Небольшой хелпер `_unwrap()` в
`product_images.py` существует только потому, что ответ загрузки должен
выбрать статус-код по флагу `replaced` мутации до второго вызова — форма, в
которую `match_result` не вписывается.

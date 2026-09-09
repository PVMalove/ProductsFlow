# ProductsFlow

Сервис учёта товаров (catalog-service), аутентификации (identity-service) и поддержки (support-service), расширяемый commerce-контекстами checkout, inventory и payment.

## Роли

**Владелец (Owner)**:
Пользователь, создавший Товар (`Product.user_id`). Владение не передаётся — операции переноса Товара другому пользователю нет.
_Avoid_: Автор, создатель

**Наблюдатель (Viewer)**:
Тот, кто запрашивает Товар(ы) на чтение — Администратор, обычный Пользователь или анонимный запрос. Анонимный и обычный (не-владелец, не-админ) Наблюдатель видят один и тот же набор Товаров — к ним применяется одно и то же правило видимости.
_Avoid_: Пользователь — когда речь именно о чтении, а не о личности

**Администратор (Admin)**:
Пользователь с ролью `UserRole.ADMIN`. Видит и может изменять любой Товар/Пользователя вне правил видимости и владения — единственный, кто видит Товары деактивированных Владельцев, и единственный, кто может (де)активировать чужую учётную запись.

**Инициатор действия (Actor)**:
Пользователь, зафиксированный в Audit-логе как выполнивший действие (`actor_user_id`) и представляющий текущую авторизованную личность в use case (`id`, `role`). Security-адаптер строит его из JWT и актуальной локальной identity-проекции, а handler решает, разрешено ли действие; при отсутствии контекста (саморегистрация, сидинг БД) равен самому затронутому Пользователю или Владельцу Товара.
_Avoid_: Владелец — Actor и Owner часто совпадают, но не всегда (например, Admin деактивирует чужой Товар — тогда Actor ≠ Owner)

**Удаление Пользователя**:
Необратимое прекращение учётной записи по инициативе самого Пользователя. Оно не является Деактивацией: удалённый Пользователь не может быть вновь активирован, а связанные с ним Тикеты сохраняются анонимизированными и закрытыми.
_Avoid_: Деактивация, блокировка, временное отключение

**Анонимизированное надгробие Пользователя**:
Сохранённая учётная запись удалённого Пользователя, из которой исключены персональные данные и возможность аутентификации. Она удерживает только необходимую историческую идентичность для неизменяемого Audit-лога и не может быть возвращена в активное состояние.
_Avoid_: Активный Пользователь, деактивированный Пользователь

## Support

Support — bounded context обращений Пользователей в службу поддержки и их переписки с командой поддержки.

### Обращения

**Тикет**:
Обращение, созданное Пользователем и принадлежащее одному Автору тикета до его удаления. Тикет объединяет тему, жизненный цикл и Сообщения тикета.
_Avoid_: Conversation, case, request

**Сообщение тикета**:
Запись переписки внутри одного Тикета, опубликованная Автором тикета либо Администратором поддержки. Оно может быть отредактировано или удалено по отдельным правилам жизненного цикла.
_Avoid_: Comment, reply

**Первое сообщение**:
Обязательное первое Сообщение тикета, создаваемое вместе с Тикетом и содержащее текст первоначального обращения.
_Avoid_: Description, body

**Удалённое сообщение**:
Сообщение тикета, чей исходный текст очищен и заменён маркером удаления, но чья позиция в истории, авторская метка и момент создания сохранены.
_Avoid_: Erased message

**Системное сообщение**:
Неизменяемое Сообщение тикета, созданное Support вследствие системного события, а не человеком.
_Avoid_: Bot reply

**Автор тикета**:
Пользователь, создавший Тикет. После удаления Пользователя ссылка на Автора тикета и на его Сообщения тикета анонимизируется; активный Тикет закрывается Системным сообщением.
_Avoid_: Owner, customer

### Жизненный цикл

**Статус тикета**:
Наблюдаемое состояние обработки Тикета: `OPEN`, `IN_PROGRESS`, `RESOLVED` или `CLOSED`.
_Avoid_: State, phase

**Закрытый тикет**:
Тикет в терминальном статусе `CLOSED`; обычная переписка и переходы статуса для него недоступны.
_Avoid_: Archived ticket

**Администратор поддержки**:
Актор с JWT-ролью `admin`, который видит все Тикеты, отвечает в них, управляет статусом и модерирует Сообщения тикета.
_Avoid_: Support agent, operator, manager

## Товар: существование и видимость

**Существование продукта**:
Товар удаляется из БД безвозвратно и мгновенно — soft-delete/архивного состояния для самого факта существования строки нет. Удалённый Товар не найден на прямых запросах, но его Audit-лог переживает удаление (хранится без ссылки на строку `products`) и остаётся доступен Владельцу/Admin. Различие между «никогда не существовал» (не найден, без записей в audit-логе) и «удалён» (не доступен для не-admin при наличии audit-лога) — осознанное решение; не пересматривается без отдельной задачи.

**Активный / деактивированный товар**:
`Product.is_active` — независимое от Владельца поле, переключаемое самим Владельцем или Admin. Деактивированный Товар скрыт из всех list/search-запросов для всех Наблюдателей, включая собственного Владельца — списки не персонализированы. Исключение действует только при прямом обращении по ID: там Владелец (и Admin) видит свой деактивированный Товар.
_Avoid_: Удаление, soft delete — Деактивация обратима и не затрагивает существование строки в БД

**Удаление**:
Необратимое удаление строки Товара из БД. Полностью независимо от Деактивации: можно удалить активный Товар, и нельзя «восстановить» удалённый переключением `is_active`.
_Avoid_: Деактивация, скрытие

**Обновление товара**:
Операция обновления меняет только явно присланные поля — `name`/`category`/`price`/`description` в схеме частичного обновления следуют одному и тому же `Optional`-паттерну, а репозиторий применяет их через `exclude_unset`. Отсутствующее в запросе поле не трогается и не сбрасывается на дефолт. Операция обновления не переключает `is_active` — для этого есть отдельные операции активации/деактивации (см. «Активный / деактивированный товар» выше).
_Avoid_: Полная замена объекта

**Видимость продуктов деактивированных владельцев**:
Если Владелец Товара деактивирован (`User.is_active=False`), все его Товары скрыты от всех Наблюдателей, кроме Admin, — независимо от собственного `is_active` Товара. Деактивированный Владелец не может пройти аутентификацию, поэтому сценария «деактивированный владелец видит своё owner-исключение» структурно не существует.

**Картинка товара**:
Не более одной записи `ProductImage` на Товар (ключ объекта в S3-совместимом приватном хранилище, тип содержимого, размер, время последнего изменения), из которой по запросу собирается временная presigned-ссылка (см. ADR 0008). Видимость Картинки полностью производна от видимости самого Товара — отдельной проверки нет: если Товар скрыт от конкретного Наблюдателя, Картинка для него так же недоступна, даже если запись физически существует в БД. «У Товара нет Картинки» — состояние, отдельное от «Товар не найден/не виден».

Создаётся или заменяется одним и тем же вызовом — вызывающая сторона не обязана заранее знать, была ли у Товара Картинка: строка `ProductImage` создаётся или обновляется одним SQL-upsert по `product_id` (см. ADR 0008). Права — только Владелец Товара или Admin, иначе отказ в доступе. Удаляется отдельной операцией; если у видимого вызывающему Товара Картинки нет — ошибка "не найдено". Ключ объекта в хранилище стабилен (`products/{id}/image`, без расширения формата в имени) — повторная загрузка тому же Товару перезаписывает один и тот же объект. Общий seed-объект (`seed/placeholder.jpg`), на который изначально указывают Картинки многих сидированных Товаров, никогда не удаляется (см. ADR 0008). Оба мутирующих действия пишутся в Audit-лог Товара (`IMAGE_UPDATED`/`IMAGE_DELETED`) — задокументированное исключение из общего правила «Audit-лог создаётся автоматически через ORM-события» (ADR 0007/0008), см. ADR 0008.
_Avoid_: Фото, изображение — в коде и API это «Картинка» (`ProductImage`, «нет картинки»)

## Прочее

## Наблюдаемость

**Контекст трассировки Outbox**:
W3C-контекст исходной операции, сохранённый вместе с доменным событием в Outbox и передаваемый в RabbitMQ, чтобы обработка события оставалась частью того же распределённого трейса.
_Avoid_: Контекст publisher-процесса, отдельный trace события

**Коррелируемый журнал**:
Структурированная JSON-запись приложения с `trace_id`, пригодная для перехода из Loki к соответствующему трейсу в Tempo. JSON-формат включается только для monitoring overlay; обычная dev-консоль остаётся человекочитаемой.
_Avoid_: Неструктурированный лог для корреляции

**Audit-лог (Audit trail)**:
Неизменяемая запись о создании/изменении/удалении/(де)активации Пользователя или Товара с указанием Инициатора действия. Создаётся автоматически на уровне ORM, а не явным вызовом в коде репозитория/роутера (см. ADR 0007 для Пользователя, ADR 0008 для Товара) — кроме мутаций Картинки товара (`IMAGE_UPDATED`/`IMAGE_DELETED`), которые идут через raw SQL upsert в обход ORM unit-of-work и поэтому пишутся явно (см. ADR 0008). У Support-сервиса отдельного Audit-лога нет — история обращения восстанавливается из треда Сообщений тикета (см. ADR 0009).
_Avoid_: История изменений, лог событий

**Курсор (keyset-пагинация)**:
Непрозрачный base64-токен, кодирующий позицию последнего элемента страницы. По умолчанию это `(created_at, id)`, но состав курсора является динамическим и зависит от выбранной сортировки (например, `(price, id)` для сортировки по цене или `(rank, id)` для полнотекстового поиска). Используется вместо номера страницы во всех list-запросах (см. ADR 0006).
_Avoid_: Номер страницы, offset

**Постраничная пагинация (offset)**:
`page_index`/`page_size`-пагинация глобального audit-фида — единственное намеренное исключение из Курсора, обоснованное тем, что `ProductAuditLog` неизменяем (см. ADR 0006, ADR 0008). Не используется больше нигде в API.
_Avoid_: Курсор — для этого конкретного эндпоинта это не то же самое понятие

**BFF API**:
HTTP API, потребляемый frontend приложения; его бизнесовые endpoint'ы используют единый конверт ответа. JWKS, health checks, внутренние worker-триггеры и OAuth2 token endpoint для стандартного OAuth2-клиента не относятся к BFF API.
_Avoid_: Любой HTTP endpoint

## Commerce

Commerce contexts manage customer checkout, inventory availability, and payment for purchases.

### Ordering

**Cart**:
A server-side, customer-owned collection of intended purchase lines that exists before an Order is created.
_Avoid_: Basket, client cart

**Cart Line**:
A requested quantity of one product in a Cart; it is mutable until checkout.
_Avoid_: Order line, item

**Order**:
The customer’s immutable commercial commitment created from a Cart at checkout, with its own lifecycle and a fixed commercial snapshot.
_Avoid_: Purchase, transaction

**Order Line**:
A product, requested quantity, unit price, discount, and product description captured inside an Order.
_Avoid_: Cart line, item

**Commercial Snapshot**:
The price, discount, currency, and product data recorded in an Order at checkout, independent of subsequent catalogue changes.
_Avoid_: Current price, live product

**Money**:
A monetary amount in Russian rubles represented as an integer number of kopecks in the first release.
_Avoid_: Float price, decimal amount

**Checkout Quote**:
The authoritative response from Catalog that validates requested products and supplies the commercial data from which an Order snapshot is made.
_Avoid_: Client price, price lookup

**Partial Checkout**:
The checkout outcome in which an Order contains only Cart Lines that Inventory can reserve; unavailable Cart Lines are not ordered.
_Avoid_: Partial payment, backorder

**Pending Order**:
An Order whose checkout process has started but has not yet reached capture or a terminal failure.
_Avoid_: Draft cart, completed order

**Unavailable Cart Line**:
A Cart Line that Inventory did not reserve during checkout and that remains in the Cart with that outcome.
_Avoid_: Cancelled order line, rejected order

**Checkout Selection**:
The versioned set of Cart Lines frozen when checkout starts; it cannot be changed until its Saga reaches a terminal result.
_Avoid_: Live cart, order line

**Order Cancellation**:
The customer-requested termination of a Pending Order before capture, requiring reversal of its outstanding reservations and payment authorization.
_Avoid_: Refund, return

**Order Status**:
The customer-visible lifecycle state of an Order: `PENDING`, `COMPLETED`, `CANCELLED`, `EXPIRED`, or `FAILED`.
_Avoid_: Saga step, message status

**Saga Step**:
The durable internal stage of checkout coordination, distinct from an Order Status.
_Avoid_: Order status, event status

**Anonymized Order**:
An Order retained for financial and operational records after its customer's identity has been removed, with `customer_id` removed and without personally identifying customer data.
_Avoid_: Deleted order, customer order

### Inventory

**Available Stock**:
The quantity of a product that Inventory may allocate to new reservations.
_Avoid_: On-hand stock, free balance

**Inventory Pool**:
The one logical stock location from which the first release allocates a product.
_Avoid_: Warehouse network, fulfilment route

**Stock Adjustment**:
An audited administrator-authorized change to a product’s Available Stock.
_Avoid_: Direct database edit, catalogue update

**Inventory Reservation**:
A time-limited allocation of a product quantity to one Order, which prevents that quantity being allocated again before it is confirmed or released.
_Avoid_: Hold, stock lock

**Reservation Expiry**:
The moment after which an unconfirmed Inventory Reservation is released and can no longer support its Order.
_Avoid_: Cancellation, payment expiry

**Allocation**:
The reversible assignment of a reserved quantity to an authorized Order before funds are captured and before fulfillment consumes it.
_Avoid_: Irreversible stock deduction, reservation

### Payments

**Payment Authorization**:
A payment provider’s reversible approval to hold an Order amount before funds are captured.
_Avoid_: Charge, payment

**Capture**:
The operation that converts a Payment Authorization into a completed transfer of funds.
_Avoid_: Authorize, charge

**Payment Reconciliation**:
The determination of a payment operation’s actual outcome from its provider and idempotency key after its response is unknown.
_Avoid_: Retry, manual payment check

**Test PSP**:
A deterministic simulated payment provider used to exercise authorization, void, capture, and reconciliation without transferring real funds.
_Avoid_: Production payment provider, mock payment

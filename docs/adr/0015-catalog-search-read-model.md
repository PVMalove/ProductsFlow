# 0015. Catalog: поисковая read-model на OpenSearch

**Статус:** Accepted.

Публичный поиск Catalog строится как самостоятельная CQRS read-model в OpenSearch: в выдачу попадают только активные Товары активных Владельцев. `catalog-service` публикует самодостаточные snapshot-события `product.*.v2`, а проекция также потребляет изменения Владельца и хранит `owner_is_active` в документе; это устраняет синхронное дочитывание write-БД в рабочем пути индексатора и сохраняет корректность видимости при eventual consistency.

`GET /api/v1/products/search` остаётся публичным BFF endpoint'ом и использует keyset-пагинацию OpenSearch `search_after`; курсор включает поля выбранной сортировки и `id` как обязательный tie-breaker. Redis хранит готовый ответ по нормализованному набору параметров ровно 60 секунд. Поэтому P99-актуальность индекса составляет не более 10 секунд, а максимальная свежесть HTTP-ответа — 70 секунд.

Полное переиндексирование не полагается на RabbitMQ как на event log: оно читает консистентный bulk-снимок PostgreSQL в новый versioned index, параллельно принимает события, выполняет reconciliation scan и атомарно переключает alias. У каждого Product есть персистентная, строго возрастающая `search_revision`; она передаётся OpenSearch как external document version, чтобы данные bootstrap не перезаписывали более новые события.

Search worker хранит собственную устойчивую `Owner Search State`. Product-событие получает `owner_is_active` из неё, а отсутствие записи означает `false`; `user.activated/deactivated/deleted` обновляют это состояние и массово меняют документы соответствующего Владельца. Тем самым порядок сообщений между Identity и Catalog не может открыть скрытый Товар через поиск.

В Redis кэшируется только первая страница: ключ включает нормализованный текстовый запрос, фильтры, сортировку и limit. Cursor-страницы не кэшируются, чтобы не допустить неограниченного роста ключей. Ошибочное сообщение после ограниченных retries переводится в DLQ с alert'ом; поток не блокируется, а расхождения исправляются reconciliation scan.

Полные self-contained snapshots публикуются только как `product.*.v2`; v1 не поддерживается и не публикуется параллельно. Это не меняет ограничение RabbitMQ: v2 достаточно для обработки доставленного сообщения, но не для исторического произвольного replay, поэтому PostgreSQL остаётся источником bootstrap/reindex.

`q` у search endpoint обязателен и ограничен 2–100 символами. Текст товара индексируется в RU- и EN-анализируемых полях; `name` имеет вес 3, `description` — 1, а `fuzziness=AUTO` доступен только для слов длиной от 3 символов. Категория представлена нормализованным keyword-полем для case-insensitive exact filter. Ночной throttled reconciliation scan дополняет targeted replay/reindex после DLQ-инцидента.

`search_revision` начинается с 1 и увеличивается в одной транзакции с create, изменением индексируемых полей, (де)активацией или удалением Product. Мутации Картинки её не меняют. Все такие v2-события несут итоговую ревизию; удаление публикует минимизирующий данные tombstone `{product_id, search_revision, user_id}`, который удаляет документ только при более новой версии.

Лаг проекции измеряется от `outbox.occurred_at` до успешной записи OpenSearch; его P99, возраст oldest pending event и размер DLQ алертятся при превышении 10 секунд или при любом DLQ-сообщении. Дополнительно собираются OpenSearch latency и cache hit ratio. MVP рассчитан на до 100 000 Товаров и 50–100 QPS: один primary shard и один replica shard; replica требует отдельного data-node для actual availability.

Поиск остаётся частью bounded context Catalog: публичный endpoint расположен в `catalog-service`, а `catalog-search-worker` — отдельный инфраструктурный процесс того же сервиса. В dev/test OpenSearch работает на одном узле с одним primary и без replica; production требует не менее двух data-node для одного primary и одного replica. OpenSearch и Redis не получают публичных host-портов в production: доступ к ним имеют только Catalog API, search worker и внутренний reindex-job.

Приёмка включает unit-тесты v2 snapshots, revision и search cursor; интеграционные тесты OpenSearch/Redis для маппинга, TTL и видимости; worker-тесты out-of-order owner/product-событий, DLQ и tombstone; и E2E публичного API для поиска, фильтров, сортировок и eventual consistency в пределах 70 секунд.

## Considered Options

- Elasticsearch отклонён в пользу OpenSearch: для self-hosted/managed развёртывания выбран Apache 2.0-лицензированный движок.
- Дочитывание Product из PostgreSQL на каждое событие отклонено: оно делает индексатор зависимым от доступности и нагрузки write-модели.
- Ролевая персонализация поискового индекса не входит в MVP: владелец и Admin работают со скрытыми Товарами через существующие прямые запросы Catalog.

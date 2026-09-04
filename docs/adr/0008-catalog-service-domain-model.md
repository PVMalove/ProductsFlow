# 0008. Catalog: доменная модель и бизнес-правила

**Статус:** Accepted. Общий канон слоёв/CQRS/UoW/GUID/пагинации — [ADR 0006](0006-service-internal-architecture-baseline.md).

`catalog-service` владеет агрегатом `Product`.

## Видимость товара

Видимость — пересечение (AND) трёх независимых условий, не одно поле:

1. **Публичный доступ без витрины за авторизацией.** Все четыре продукт-list-эндпоинта (`GET /products`, `/search`, `/price-range`, `/category/{name}`) и `GET /products/{id}` — публичны, без обязательной аутентификации. Токен при этом не терпим к невалидности: если он передан и невалиден/просрочен/принадлежит деактивированному аккаунту — запрос завершается `401`/`403`, а не тихим откатом к анонимному просмотру. Мутации (`POST`/`PATCH`/`DELETE`) остаются под `CurrentUser`; `/audit` — под `AdminUser`/owner-or-admin.
2. **`Product.is_active`** — самостоятельное, независимое от владельца поле, переключаемое владельцем товара или `ADMIN` (`PATCH /products/{id}/activate`/`/deactivate`). Деактивированный товар скрыт из всех list/search-запросов для всех наблюдателей, включая собственного владельца — списки не персонализированы. Исключение — прямой доступ по ID: там владелец (и admin) видит свой деактивированный товар.
3. **Видимость по владельцу.** Если владелец товара деактивирован (`User.is_active=False`), все его товары скрыты от всех наблюдателей, кроме `ADMIN`, независимо от собственного `is_active` товара, кроме короткого окна eventual-consistency — [ADR 0011](0011-catalog-service-event-integration.md).

Удаление товара — необратимое и независимое от деактивации: hard-delete строки, отдельная операция, не переключение `is_active`.

## PATCH, не PUT

`PATCH /products/{id}` — частичное обновление, `exclude_unset`; непереданные поля не трогаются и не сбрасываются на дефолт. `PUT` для этого пути не зарегистрирован (`405`). Обновление никогда не переключает `is_active` — для этого отдельные операции активации/деактивации.

## Картинка товара: upsert одним запросом, стабильный ключ, ручной audit

Не более одной `ProductImage` на товар. `POST /products/{id}/image` обслуживает и создание, и замену одним вызовом: `INSERT ... ON CONFLICT (product_id) DO UPDATE ... RETURNING`, а не read-then-branch.

- **S3-ключ стабилен и без расширения формата** — `products/{product_id}/image`; повторная загрузка перезаписывает тот же объект, `Content-Type` — заголовком объекта, не именем ключа. Объекты с префиксом `seed/` (общий плейсхолдер сидированных товаров) никогда не удаляются, иначе замена картинки одного товара сломала бы плейсхолдер у всех остальных.
- **Публичный доступ к объекту — presigned URL, не публичная read-политика бакета.** `catalog-service` отдаёт клиенту временную подписанную ссылку на конкретный объект через `build_presigned_url`; сам бакет остаётся приватным.
- **Audit — явная запись в обход ORM-событий.** `upsert_product_image`/`delete_product_image` пишут `ProductAuditLog` явно, в том же repository-методе и в той же транзакции, что и сам upsert/delete (`IMAGE_UPDATED`/`IMAGE_DELETED`) — задокументированное исключение из правила ниже: raw SQL upsert физически не проходит через ORM `Session`-флаш, на котором висят `@event.listens_for`-слушатели.

## Audit trail через ORM event listeners

Мутации `Product` (создание/изменение/удаление/(де)активация) логируются через `@event.listens_for(ProductModel, "after_insert"/"before_update"/"before_delete")` в `infrastructure/db/audit.py`, не явными вызовами в repository/router. Actor — тот же `observability.context.actor_id_var` ([ADR 0005](0005-security-auth-actor-contract.md)).

- **`ProductAuditLog.product_id` — намеренно без `ForeignKey`** (в отличие от identity, [ADR 0007](0007-identity-service-domain-model.md)): `Product`, в отличие от `User`, удаляется физически (hard delete, не Tombstone); `before_delete`-listener должен успеть вставить audit-строку для только что удаляемого товара — внешний ключ на исчезающую строку это бы заблокировал.
- Мутации картинки — задокументированное исключение из этого правила (см. выше).

## Пагинация: cursor для списков, offset для audit-фида

`GET /products`/`/search`/`/price-range`/`/category/{name}` пагинируются общим keyset-контрактом ([ADR 0006](0006-service-internal-architecture-baseline.md)) по `(created_at, id)`. `GET /products/audit` (admin-фид `ProductAuditLog`) — исключение в offset-стиле: audit-строки неизменяемы и не подвержены дрейфу, а admin-фиду ценнее `total`/`total_pages`, которые курсор не даёт.

## Единая версия API

`catalog-service` не разводит `/api/v1`/`/api/v2` — см. [ADR 0004](0004-api-gateway-and-routing.md).

## Consequences

- Видимость товара определяется тремя правилами сразу — читатель кода не может понять её по одному из них в отдельности.
- Presigned URL для картинки — единственная точка, где `catalog-service` отдаёт клиенту прямую ссылку на инфраструктуру хранения; срок жизни ссылки и её инвалидация при замене картинки — забота адаптера `S3Storage`, не домена.

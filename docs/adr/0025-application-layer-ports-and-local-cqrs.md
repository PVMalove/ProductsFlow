# 0025. Application владеет use case; CQRS — локальная опция

**Статус:** Superseded [ADR 0027](0027-domain-repository-contracts.md)\
**Дата:** 2026-09-01\
**Связанные issues:** #63, #156–#160, #163

Этот ADR зафиксировал локальные command/query и handler-правила для
application-слоя, но ошибочно поместил контракты repository в application.
Решение о владельце repository-контрактов заменено ADR 0027: они принадлежат
domain bounded context, а application использует их как зависимости use case.

CQRS остаётся локальной опцией для сложных или нагруженных сценариев. В
проекте нет общего `ICommand`/`IQuery`, handler-Protocol, dispatcher, registry
или pipeline behavior.

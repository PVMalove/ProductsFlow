# 0027. Repository-контракт принадлежит domain

**Статус:** Accepted\
**Дата:** 2026-09-01\
**Supersedes:** [ADR 0025](0025-application-layer-ports-and-local-cqrs.md)\
**Связанные issues:** #156–#160

Контракт repository — часть bounded context агрегата и живёт в
`<service>/src/domain/repositories.py`. Он описывает операции, необходимые для
сохранения и чтения доменного агрегата, не импортирует application,
infrastructure, SQLAlchemy или FastAPI и не переезжает в `kernel-domain`.

`application/` владеет use case и импортирует доменный `ProductRepository` для
типизации своих зависимостей. `infrastructure/` содержит реализации этого
контракта. Для одного агрегата concrete-реализация использует нейтральное имя
`ProductRepository` в своём infrastructure-модуле; технология хранения не
становится частью доменного имени.

`owner_read_model` и другие внешние gateway-контракты не становятся частью
этого repository: их выделение решается отдельными use case и ADR только при
появлении реальной потребности.

# Git workflow: feature branch + PR

### 1. Fundamental Constraints & Tooling
* **Zero Direct Commits:** Any direct commits to the main branch (`master`/`main`) or the current working branch are strictly prohibited unless it is an isolated feature branch.
* **CLI Only:** Rely exclusively on `git` and GitHub CLI (`gh`) tools for repository and task operations.
* **Issue First:** No development begins without a registered ticket. All implementation tasks MUST be created beforehand using `gh issue create`.

### 2. Workflow Sequence

1. **Initialization (Branching):**
   An isolated branch is created for each task.
   * **Format:** `feature/issue-<ID>-<краткое_описание_задачи_на_русском>` (where `<ID>` is the GitHub issue number and the suffix is a short Russian-language slug of the task, words separated by underscores — e.g. `feature/issue-42-исправление_валидации_email`).
   * **Command:** `git checkout -b feature/issue-<ID>-<краткое_описание>`
2. **Post-branch Push:**
   * Immediately after creating the branch, push it to GitHub so it exists remotely: `git push -u origin feature/issue-<ID>-<краткое_описание>`.
3. **Implementation & Quality Assurance (TDD):**
   * Code MUST be written in strict accordance with the **TDD** (Test-Driven Development) methodology.
   * Local testing is mandatory before committing any changes.
4. **Committing Changes:**
   * Commits are made only to the current feature branch.
   * Commit messages **MUST** follow the **Semantic Commit Messages** standard (e.g., `feat: ...`, `fix: ...`, `refactor: ...`).
5. **Continuous Push:**
   * Push commits to GitHub both while implementing the task and after addressing code-review feedback: `git push origin feature/issue-<ID>-<краткое_описание>`. Never leave finished commits sitting only in the local repo.
6. **Integration (Pull Request):**
   * PR creation is performed automatically via CLI: `gh pr create`.
   * **Mandatory Requirement:** The pull request body MUST contain the phrase `Closes #<ID>` to automatically link and close the original ticket upon successful merge.
   * **Mandatory Requirement:** The pull request body MUST contain the commented checklist block from [§3 PR Body Template](#3-pr-body-template), in Russian, followed by the seven sections it describes filled in with the actual content of the change.

### 3. PR Body Template

Every `gh pr create --body` MUST start with the following HTML comment verbatim (invisible when GitHub renders the PR, but a checklist for the author and a navigator for the reviewer — required in Russian because the domain and review process are Russian-language), followed by the seven sections it describes, filled in for the actual change:

```html
<!--
Этот закомментированный блок в теле Pull Request служит чек-листом для автора и навигатором для ревьюера. Поскольку в Enterprise-разработке (особенно в распределенных системах, микросервисах и сложной предметной области) цена ошибки высока, каждый пункт должен давать четкое понимание контекста изменений.

1. Итог
Краткая выжимка того, какая конечная цель достигнута этим пулл-реквестом. Читая только этот пункт, ревьюер должен понять суть PR без погружения в код.
Что писать: Суть решенной проблемы или добавленной фичи в 1–2 предложениях.
Пример: «Завершен рефакторинг логики управления клиентами: старый легаси-код переведен на использование паттерна Specification и изолирован в отдельном микросервисе.»

2. Затронутые части проекта
Указание конкретных модулей, слоев архитектуры, сервисов или баз данных, которые были изменены. Это помогает ревьюерам сразу понять масштаб влияния (impact).
Что писать: Названия микросервисов, слои (Domain, Infrastructure, Application, API), схемы БД или конфигурационные файлы инфраструктуры.
Пример: «Application layer (команды и хэндлеры), Infrastructure (настройки IDefaultRepository), конфигурация мониторинга (Loki).»

3. Бизнес-логика
Описание изменений в правилах предметной области (домена). Здесь фокус смещается с кода на бизнес-правила.
Что писать: Какие бизнес-правила добавлены, изменены или удалены. Как теперь должна вести себя система с точки зрения бизнеса.
Пример: «Изменена логика обновления данных учредителей: теперь нельзя удалить учредителя через RemoveFounder, если за ним числятся активные договоры. Добавлена валидация на уровне корня агрегата (Aggregate Root).»

4. Что изменено
Техническое описание реализации. Это путеводитель по вашим коммитам для ревьюера.
Что писать: Использованные технические паттерны, добавленные классы/интерфейсы, изменения в сигнатурах методов или структурах данных.
Пример: «Добавлен UpdateFounderCommandHandler (CQRS). Доработана модель данных. Оптимизированы DAX-меры для расчетов MTBF/MTBR.»

5. Проверка
Подтверждение того, что код работает и соответствует стандартам качества (TDD).
Что писать: Как именно тестировался функционал (Unit-тесты, интеграционные, E2E, ручная проверка).
Пример: «Бизнес-логика агрегатов покрыта unit-тестами (xUnit, Moq). Интеграция с базой данных проверена через Testcontainers. Локально протестировано через Swagger.»

6. Не проверено и риски
Самый важный пункт для управления техническим долгом и инцидентами. Честное признание узких мест.
Что писать: Краевые случаи (edge cases), которые не покрыты тестами, потенциальные проблемы с производительностью при больших объемах данных, или "костыли", оставленные до следующей итерации.
Пример: «Риск: новый сложный запрос может деградировать по производительности при объеме данных >1 млн записей. Не проверялась работа при недоступности S3-хранилища (MinIO), требуется отдельная задача на реализацию Circuit Breaker.»

7. Интеграция
Инструкция для DevOps или релиз-инженера по развертыванию этого кода в других окружениях (dev/stage/prod).
Что писать: Требуется ли накатить миграции БД, добавить новые переменные окружения, обновить секреты, или есть ли зависимость от других PR.
Пример: «Перед деплоем необходимо выполнить миграции БД. Добавить новую переменную окружения MINIO_ENDPOINT в Kubernetes-манифесты.»
-->
```

Followed by the visible, filled-in sections:

```markdown
## Итог

## Затронутые части проекта

## Бизнес-логика

## Что изменено

## Проверка

## Не проверено и риски

## Интеграция

Closes #<ID>
```

<!-- ### 1. Фундаментальные ограничения и инструментарий

* **Zero Direct Commits:** Строго запрещены любые прямые коммиты в главную ветку (`master`/`main`) или текущую рабочую ветку, если это не изолированная ветка задачи.
* **CLI Only:** Для управления репозиторием и задачами используются исключительно утилиты командной строки `git` и GitHub CLI (`gh`).
* **Issue First:** Никакая разработка не начинается без зафиксированного тикета. Все задачи на реализацию должны быть предварительно созданы через `gh issue create`.

### 2. Жизненный цикл разработки (Workflow Sequence)

1. **Инициализация задачи (Branching):**
Для каждой задачи создается изолированная ветка.
* **Формат:** `feature/issue-<ID>-<краткое_описание_задачи_на_русском>` (где `<ID>` — номер задачи в GitHub, а суффикс — короткое описание задачи на русском, слова через нижнее подчеркивание).
* **Команда:** `git checkout -b feature/issue-<ID>-<краткое_описание>`


2. **Push ветки сразу после создания:**
* Сразу после создания ветки она отправляется в GitHub: `git push -u origin feature/issue-<ID>-<краткое_описание>`.


3. **Разработка и контроль качества (Implementation & TDD):**
* Код пишется в строгом соответствии с методологией **TDD** (Test-Driven Development).
* Локальное тестирование обязательно до фиксации изменений.


4. **Фиксация изменений (Committing):**
* Коммиты выполняются только в текущую feature-ветку.
* Сообщения коммитов **обязаны** соответствовать стандарту **Semantic Commit Messages** (например, `feat: ...`, `fix: ...`, `refactor: ...`).


5. **Регулярный push:**
* Коммиты отправляются в GitHub как по ходу выполнения задачи, так и после каждого раунда code review: `git push origin feature/issue-<ID>-<краткое_описание>`. Готовые коммиты не должны оставаться только локально.


6. **Интеграция (Pull Request):**
* Открытие PR выполняется автоматически через CLI: `gh pr create`.
* **Обязательное требование:** Тело пулл-реквеста должно содержать фразу `Closes #<ID>` для автоматического связывания и закрытия исходного тикета при успешном слиянии (merge).
* **Обязательное требование:** Тело пулл-реквеста должно начинаться с закомментированного чек-листа из раздела «3. PR Body Template» выше (текст уже на русском), а далее содержать заполненные семь разделов, которые он описывает. -->

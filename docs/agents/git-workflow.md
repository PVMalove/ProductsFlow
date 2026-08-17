# Git workflow: feature branch + PR

### 1. Fundamental Constraints & Tooling
* **Zero Direct Commits:** Any direct commits to the main branch (`master`/`main`) or the current working branch are strictly prohibited unless it is an isolated feature branch.
* **CLI Only:** Rely exclusively on `git` and GitHub CLI (`gh`) tools for repository and task operations.
* **Issue First:** No development begins without a registered ticket. All implementation tasks MUST be created beforehand using `gh issue create`.

### 2. Workflow Sequence

1. **Initialization (Branching):**
   An isolated branch is created for each task.
   * **Format:** `feature/issue-<ID>` (where `<ID>` is the GitHub issue number).
   * **Command:** `git checkout -b feature/issue-<ID>`
2. **Implementation & Quality Assurance (TDD):**
   * Code MUST be written in strict accordance with the **TDD** (Test-Driven Development) methodology.
   * Local testing is mandatory before committing any changes.
3. **Committing Changes:**
   * Commits are made only to the current feature branch.
   * Commit messages **MUST** follow the **Semantic Commit Messages** standard (e.g., `feat: ...`, `fix: ...`, `refactor: ...`).
4. **Synchronization (Push):**
   * Push the branch to the remote repository: `git push origin feature/issue-<ID>`.
5. **Integration (Pull Request):**
   * PR creation is performed automatically via CLI: `gh pr create`.
   * **Mandatory Requirement:** The pull request body MUST contain the phrase `Closes #<ID>` to automatically link and close the original ticket upon successful merge.

<!-- ### 1. Фундаментальные ограничения и инструментарий

* **Zero Direct Commits:** Строго запрещены любые прямые коммиты в главную ветку (`master`/`main`) или текущую рабочую ветку, если это не изолированная ветка задачи.
* **CLI Only:** Для управления репозиторием и задачами используются исключительно утилиты командной строки `git` и GitHub CLI (`gh`).
* **Issue First:** Никакая разработка не начинается без зафиксированного тикета. Все задачи на реализацию должны быть предварительно созданы через `gh issue create`.

### 2. Жизненный цикл разработки (Workflow Sequence)

1. **Инициализация задачи (Branching):**
Для каждой задачи создается изолированная ветка.
* **Формат:** `feature/issue-<ID>` (где `<ID>` — номер задачи в GitHub).
* **Команда:** `git checkout -b feature/issue-<ID>`


2. **Разработка и контроль качества (Implementation & TDD):**
* Код пишется в строгом соответствии с методологией **TDD** (Test-Driven Development).
* Локальное тестирование обязательно до фиксации изменений.


3. **Фиксация изменений (Committing):**
* Коммиты выполняются только в текущую feature-ветку.
* Сообщения коммитов **обязаны** соответствовать стандарту **Semantic Commit Messages** (например, `feat: ...`, `fix: ...`, `refactor: ...`).


4. **Синхронизация (Push):**
* Отправка ветки в удаленный репозиторий: `git push origin feature/issue-<ID>`.


5. **Интеграция (Pull Request):**
* Открытие PR выполняется автоматически через CLI: `gh pr create`.
* **Обязательное требование:** Тело пулл-реквеста должно содержать фразу `Closes #<ID>` для автоматического связывания и закрытия исходного тикета при успешном слиянии (merge). -->

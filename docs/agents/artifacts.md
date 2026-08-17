### Artifacts & Scratchpads Management

* **Storage Location:** NEVER use system temporary directories (e.g., `AppData/Local/Temp`) for saving specifications, scratchpads, or intermediate files.
* **Project Directory:** All intermediate task-related documents MUST be saved locally inside the project repository in the `docs/tasks/` directory (create it if it doesn't exist).
* **Naming Convention:** Every specification or scratchpad file MUST include the GitHub Issue ID (if it exists) and a descriptive name in its filename.
  * *Example:* `docs/tasks/issue-45-spec-product-audit-edge-cases.md`
* **Workflow:** During `/to-spec` or when creating a scratchpad or, creating roadmaps (`/wayfinder`), explicitly write the file to this directory. Do not commit these files to `master` unless explicitly asked.

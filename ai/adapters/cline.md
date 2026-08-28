# Cline Adapter

Cline loads `.clinerules/00-quantiqmt-project.md` as a short tool-specific entry. The entry points to
the same repository authority chain used by other agents:

1. `AGENTS.md`
2. `spec/README.md` and `spec/manifest.yaml`
3. the single file in `tasks/active/`
4. every task `spec_refs`
5. task `allowed_paths`, `forbidden_paths`, acceptance and `verification.commands`

不得复制业务契约到 `.clinerules` 或本 adapter。Cline-specific convenience rules cannot change
Event, Command, DTO, state machine, Repository, Workflow, task scope or safety invariant.

Start Cline at the repository root and provide only the active task ID plus the requested outcome.
If no active task exists or a dependency/path/spec conflict is found, Cline must stop and report the
exact gate instead of inventing a task or editing outside scope.

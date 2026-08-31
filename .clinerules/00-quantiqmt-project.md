# QuantiQmt Cline Entry

## Authority discovery

1. Read the root `AGENTS.md` and every closer `AGENTS.md` for a target path.
2. Read `spec/README.md`, `spec/manifest.yaml`, the single task in
   `tasks/active/`, and all of its `spec_refs`.
3. Treat those repository sources as authoritative; this tool entry does not
   restate their contracts.

## Scope and handoff gate

- Execute exactly one active task and obey its dependencies, `allowed_paths`,
  `forbidden_paths`, acceptance criteria, and `verification.commands`.
- Read `.clinerules/10-codex-handoff.md` and the Codex-authored Handoff Record
  before changing files.
- Stop with `PLAN_BLOCKED` when authority, identity, scope, cleanliness, or
  required evidence cannot be verified.

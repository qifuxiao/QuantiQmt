# Cline Adapter

Cline 是 tool/adapter，不自动等于 Implementation Agent。只有 GitHub 上可核验的人类
implementation assignment 才能分配该角色；共享角色、single-writer、Head 和 lifecycle
规则以根 `AGENTS.md` 与 `ai/workflows/team-collaboration.md` 为准。

Cline loads `.clinerules/00-quantiqmt-project.md` as a short tool-specific entry. The entry points to
the same repository authority chain used by other agents:

1. `AGENTS.md`
2. `spec/README.md` and `spec/manifest.yaml`
3. the single file in `tasks/active/`
4. every task `spec_refs`
5. task `allowed_paths`, `forbidden_paths`, acceptance and `verification.commands`
6. `.clinerules/10-codex-handoff.md` — cross-server handoff constraints,
   PLAN_BLOCKED gates, and the standard Implementation Report format

不得复制业务契约到 `.clinerules` 或本 adapter。Cline-specific convenience rules cannot change
Event, Command, DTO, state machine, Repository, Workflow, task scope or safety invariant.

When assigned as the **Implementation Agent**, Cline must read the **Codex Plan** embedded in the active task
(Plan version, Planning Base SHA, design, file-level plan, test mapping, failure
design, PLAN_BLOCKED conditions). The **Implementation/Repair Base SHA** comes
exclusively from the Codex-authored Handoff Record (`expected_base_sha`). Cline may
verify that a ref resolves to it but must not derive or write the value from
`origin/main` or the task file. After implementation, Cline
must produce an **Implementation Report** in the format defined by
`.clinerules/10-codex-handoff.md`.

## Capability-bound verification

- Linux Cline 必须运行其环境支持的全部 `portable` 命令；不得全部 skip，也不得声称已完成
  Windows 或 Mini QMT 验收。
- Windows Cline 只能按实际 OS、依赖和外部环境能力报告 `windows` evidence。只有真实可用的
  Mini QMT 环境和 task 要求具备时才能报告 `windows_miniqmt`；mock/Linux 结果不得替代。
- 每份 environment evidence 必须绑定 exact Head。Head 改变后旧证据失效并重跑；缺 required
  lane 时返回 `BLOCKED`，不得把 acceptance 改成 optional。
- assignment/evidence 必须由 `scripts/validate_agent_environment.py` 按两个正式 schema 验证；
  adapter 不解释命令或复制 machine gate。
- Cline 不得连接 Mini QMT 或发送模拟委托，除非 separate active task 和可核验人类授权同时
  明确允许；real-money trading 始终 forbidden。

Start Cline at the repository root and provide only the active task ID plus the requested outcome.
If no active task exists or a dependency/path/spec conflict is found, Cline must stop and report the
exact gate instead of inventing a task or editing outside scope.

# Workflow: Review Task

1. 独立读取 task、spec_refs 和 diff，不以实现者解释替代证据。
2. 先检查 allowed/forbidden paths 和依赖边界。
3. 按 `ai/review/trading-safety.md`、`architecture.md`、`test-quality.md` 检查。
4. 重新执行关键验证，检查失败场景而非只看 happy path。
5. Findings 按 P0–P3 排序，引用文件和行号。
6. 只有所有 acceptance criteria 有证据、无 P0/P1、验证通过，才建议移入 completed。

Review evidence must bind the verdict to an exact reviewed head SHA and PR URL. A reviewer may report historical evidence as unverified, but that state is release-prohibited and cannot unlock dependencies. Human project members own merge and the active-to-completed governance transition.

Review 结论：APPROVE、REQUEST_CHANGES 或 BLOCKED。不得 Review 自己未隔离的实现并直接批准。

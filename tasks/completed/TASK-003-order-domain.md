---
id: TASK-003
title: Implement OMS order aggregate and state machine
status: completed
depends_on: [TASK-001, TASK-002, TASK-012]
spec_refs: [INV-TRADING, INV-CONSISTENCY, SM-ORDER, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-BROKER-TRADE-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1]
allowed_paths: [src/quantiqmt/order/domain/**, tests/unit/order/**, tests/property/order/**]
forbidden_paths: [src/quantiqmt/order/infrastructure/**, src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/order tests/property/order", "poetry run mypy src/quantiqmt/order/domain"]
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: current_state_retrospective_revalidation_after_repairs
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/113
    reviewed_head_sha: f38efe13e343bba1b79c79f934c564a59839b991
    review_verdict: APPROVE
    reviewer: qifuxiao (Human GitHub Approval recording independent retrospective Review)
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/113#pullrequestreview-5139314381
    merge_commit_sha: 7ab8e66b009bc45de25732b5e7bfc505f506567d
    human_authorization_evidence: >-
      qifuxiao's APPROVED Review 5139314381 at 2026-09-08T08:36:15Z
      accepts the repair and all current TASK-003 acceptance criteria at
      f38efe13e343bba1b79c79f934c564a59839b991; PR #113 was merged at
      2026-09-08T08:36:19Z. The Human separately authorized this single-file
      record revision in the coordinating conversation from exact Base
      7ab8e66b009bc45de25732b5e7bfc505f506567d, without task activation.
    historical_change_pr: https://github.com/qifuxiao/QuantiQmt/pull/11
    historical_head_sha: 88ba9e79ec375678128d5df6710006396565a478
    historical_merge_commit_sha: 776b010162da72b11110653a3de695c55856757a
    historical_review_status: reported_unverified
---

# Objective

实现纯 Domain Order 聚合、状态迁移、Guard、领域事件和不变量。

## Acceptance criteria

- [x] YAML 中所有合法迁移覆盖，未声明迁移拒绝为 QQ-OMS-5002。
- [x] cum_quantity 单调且不超过 quantity。
- [x] UNKNOWN 不产生自动重新提交动作。
- [x] 重复/乱序输入 Property Test 保持最终不变量。
- [x] Domain 无 DB、Redis、QMT、系统时间依赖。

## Historical evidence (retained, not current acceptance)

The following original report is retained as historical text. PR #11 is
verifiably merged, but its GitHub Reviews, issue comments and inline review
comments are all empty as checked on 2026-09-08. Historical test counts and
claimed independent approvals below are not reconstructed pre-merge evidence.

- Python transition catalog 与 `SM-ORDER` 的 80 条迁移完全一致。
- Structured Guard、Broker/Trade fact identity、冲突 fingerprint、stale report 和恢复一致性均已实现。
- 多笔部分成交、撤单竞态、UNKNOWN 对账、终态迟到成交及重复/乱序重放均有单元或 Property Test 覆盖。
- `poetry run pytest tests/unit/order tests/property/order`: passed, 29 tests（独立 Review 复验）。
- Full repository pytest: passed, 242 tests（合并前实现门禁）。
- Mypy、Ruff、Spec validation: passed.
- 两个独立 Review 会话均为 `APPROVE`，无未关闭 P0-P3 findings。
- 业务实现由 PR #11 合入 `main`，merge commit `776b010`，日期 2026-07-07。

## Current retrospective acceptance

- Task: TASK-003; acceptance applies to reviewed Head
  `f38efe13e343bba1b79c79f934c564a59839b991`, not the historical PR #11 Head.
- [PR #112](https://github.com/qifuxiao/QuantiQmt/pull/112) repaired restored
  integer-version validation. Head: `f5b114914b31aed2e624092b3accd75153072184`;
  merge: `255053f390902c6f7a33168f16aac05de6f5291a` at 2026-09-08T02:41:26Z.
  Its two-file Approval alone did not establish full TASK-003 acceptance.
- [PR #113](https://github.com/qifuxiao/QuantiQmt/pull/113) repaired active-order
  proof in cancel-rejection guards. The subsequent independent retrospective
  Review covered the repair AND all five current acceptance criteria.
- [Human Approval 5139314381](https://github.com/qifuxiao/QuantiQmt/pull/113#pullrequestreview-5139314381)
  is authored by `qifuxiao` and records that independent conclusion: prior P1
  resolved, 64 task tests and 532 independent retrospective cases passed.
  The GitHub author is the Human recording/accepting the result, not a claim
  that the Human produced the independent probe. This coordinator did not
  produce an independent verdict.

Acceptance mapping (independent retrospective results accepted by that Review):

| Acceptance criterion | Current evidence |
| --- | --- |
| Legal and illegal transitions | All 80 transition/guard/action definitions matched; illegal transitions and failed guards rejected. Ten missing/terminal-status cancel-rejection cases reject as QQ-OMS-5002 without mutation. |
| Monotonic, bounded cumulative quantity | Trade-derived quantity bounds, transition assertions and Order property tests passed. |
| UNKNOWN never blindly retries | UNKNOWN dispatch rejection, reconciliation-only actions and invisible-order no-op cases passed. |
| Duplicate/out-of-order invariants | Fact replay, trade permutations, recovery, single version increment and duplicate no-op checks passed. |
| Pure Domain | Source/import audit found no DB, Redis, QMT or wall-clock calls. |

Commands and evidence scope:

- At the reviewed Head, the independent Reviewer reported
  `poetry run pytest tests/unit/order tests/property/order`: exit 0,
  64 passed, 0 skipped; cache ACL warning only.
- `poetry run mypy src/quantiqmt/order/domain`: exit 0, 2 files.
- Spec validation, focused Ruff check/format and diff check: exit 0.
- Full independent retrospective probe: 532 cases passed, exit 0; reported
  probe SHA-256 `e2155e967403694a6bd71dd05c74b796ac9302cd74a2422a55c4aa55eda30db5`.
  This is a Reviewer-reported artifact digest, not a coordinator rerun or
  a claim that the probe is committed to Git.
- The Review verified exact-Head source imports and four successful CI jobs.
  Evidence bound to the implementation Head is not represented as verification
  of this later documentation commit.

Unverified scope: historical pre-merge Review remains unavailable; current
retrospective acceptance does not backdate or manufacture it. No full-system,
local PostgreSQL or Mini QMT/account/market/trading acceptance is claimed.
Release remains prohibited. TASK-005 is not activated by this record.
No specification or acceptance criterion is changed.

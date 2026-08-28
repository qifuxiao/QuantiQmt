---
id: TASK-052
title: Revalidate TASK-004 persistence and outbox delivery evidence
status: active
depends_on: [TASK-031, TASK-043, TASK-049, TASK-050]
spec_refs: [INV-CONSISTENCY, REPO-ORDER, STORAGE-SOT, STORAGE-ORDER-PERSISTENCE, STORAGE-OUTBOX, PORTS-ORDER-PERSISTENCE, WF-ORDER-COMMIT, WF-OUTBOX-PUBLICATION, WF-RECOVERY, CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-ORDER-STATUS-V1, CONTRACT-ERROR-CATALOG]
allowed_paths:
  - tasks/active/TASK-052-task-004-delivery-revalidation.md
  - tasks/completed/TASK-052-task-004-delivery-revalidation.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - tasks/completed/TASK-004-persistence-outbox.md
  - ai/governance/task-004-delivery-revalidation-task-052.yaml
  - scripts/validate_task_052_delivery_evidence.py
  - tests/spec/test_task_052_delivery_evidence.py
  - tests/integration/persistence/test_task_052_migration_revalidation.py
forbidden_paths:
  - src/**
  - spec/**
  - migrations/**
  - tests/unit/**
  - tests/property/**
  - tests/contract/**
  - tests/integration/market/**
  - tests/integration/persistence/test_postgres_order_persistence.py
  - tests/integration/persistence/test_migration_and_ci_contract.py
  - .github/**
  - pyproject.toml
  - poetry.lock
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_task_052_delivery_evidence.py
    - poetry run pytest tests/unit/order/application/test_persistence_model.py
    - poetry run pytest tests/contract/persistence/test_order_persistence_contract.py
    - poetry run pytest tests/integration/persistence/test_migration_and_ci_contract.py
    - docker pull postgres:16
    - poetry run python -c "import json, subprocess; image=json.loads(subprocess.check_output(['docker','image','inspect','postgres:16'], text=True))[0]; digests=image.get('RepoDigests') or []; matches=[value for value in digests if '@sha256:' in value]; print('\n'.join(matches)); raise SystemExit(0 if matches else 'postgres:16 has no immutable RepoDigest')"
    - docker run --detach --rm --name quantiqmt-task-052-postgres -e POSTGRES_USER=quantiqmt -e POSTGRES_PASSWORD=quantiqmt -e POSTGRES_DB=quantiqmt_task052 -p 55432:5432 postgres:16
    - docker exec quantiqmt-task-052-postgres pg_isready -U quantiqmt -d quantiqmt_task052
    - poetry run python -c "import subprocess; value=subprocess.check_output(['docker','exec','quantiqmt-task-052-postgres','psql','-U','quantiqmt','-d','quantiqmt_task052','-Atqc','SHOW server_version_num'], text=True).strip(); print(value); raise SystemExit(0 if value.isdecimal() and 160000 <= int(value) < 170000 else f'expected PostgreSQL 16.x server_version_num, got {value!r}')"
    - poetry run python -c "import os, subprocess, sys; env={**os.environ, 'QUANTIQMT_POSTGRES_DSN':'postgresql://quantiqmt:quantiqmt@localhost:55432/quantiqmt_task052'}; raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', 'tests/integration/persistence/test_postgres_order_persistence.py', 'tests/integration/persistence/test_migration_and_ci_contract.py'], env=env))"
    - poetry run python -c "import os, subprocess, sys; env={**os.environ, 'QUANTIQMT_POSTGRES_DSN':'postgresql://quantiqmt:quantiqmt@localhost:55432/quantiqmt_task052'}; raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', 'tests/integration/persistence/test_task_052_migration_revalidation.py', '-q'], env=env))"
    - poetry run python -c "import os; from pathlib import Path; from time import monotonic_ns; from quantiqmt.order.infrastructure.postgres import PostgresOrderPersistence; store=PostgresOrderPersistence('postgresql://quantiqmt:quantiqmt@localhost:55432/quantiqmt_task052'); migrations=[path.read_text(encoding='utf-8') for path in sorted(Path('migrations').glob('*.sql'))]; [store.apply_migration(sql, deadline_monotonic_ns=monotonic_ns()+60000000000) for _ in range(2) for sql in migrations]"
    - poetry run pytest tests/unit/order/application tests/contract/persistence tests/integration/persistence
    - poetry run mypy src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure src/quantiqmt/messaging/outbox
    - poetry run ruff check src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure src/quantiqmt/messaging/outbox tests/unit/order/application tests/contract/persistence tests/integration/persistence
    - poetry run ruff format --check src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure src/quantiqmt/messaging/outbox tests/unit/order/application tests/contract/persistence tests/integration/persistence
    - poetry run python scripts/validate_task_052_delivery_evidence.py --evidence ai/governance/task-004-delivery-revalidation-task-052.yaml --repository qifuxiao/QuantiQmt
    - git diff --check origin/main...HEAD
    - git diff --name-only origin/main...HEAD
    - docker stop quantiqmt-task-052-postgres
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

在不追溯改写 TASK-004 历史事实、不修改业务实现或规范的前提下，对当前
`main` 上实际存在的 Order persistence、Journal、Snapshot、transactional
Outbox 与 Recovery 实现建立一组新的、可审计、绑定精确 Head 的交付证据。

TASK-052 是治理 revalidation，不是业务实现、release waiver 或发布授权。只有
当前规范与实现范围完整、全部 acceptance 命令在隔离 PostgreSQL 16 环境通过、
精确 Head 获得独立 `APPROVED` Review、CI 成功并合并后，才允许受控更新
TASK-004 的 delivery metadata；任何条件缺失均保持 TASK-004 `unverified`、
TASK-048 `blocked`、release prohibited。

## Human authorization

- 2026-08-28 人类明确授权：“授权创建并激活 TASK-004 delivery revalidation
  治理任务，先只做现状审计、验证范围设计和任务 PR，不修改业务实现；发现实现
  缺口时另行报告并请求授权。”
- 本授权仅覆盖 TASK-052 的只读审计、验证范围设计、激活元数据与治理 PR；不覆盖
  runtime、migration、规范、TASK-004 历史证据、TASK-048 激活、部署、发布、
  自审、批准或 merge。

## Dependency decision

- TASK-031 建立五轴 delivery state、`reported_unverified` 与可信 completion evidence
  的 fail-closed 基线；TASK-043 建立历史证据和 waiver 生命周期边界；TASK-049
  使对应 validator tests 可重复、cleanup-safe。这三项均具可信 completed delivery，
  是本治理 revalidation 的直接治理依赖。
- TASK-050 具可信 completed delivery，并冻结当前 Spec 0.14 的 broker binding、
  legacy `UNBOUND`、migration 与恢复兼容契约；TASK-052 必须以该当前契约审计
  TASK-004 实现，而不能只复验旧实现时代的规范快照。
- TASK-013 冻结 Order persistence/Journal/Snapshot/Outbox/Recovery 的规范职责，
  但其 delivery 仍是 `acceptance_status: unverified`、
  `review_status: reported_unverified`。把 TASK-013 设为直接依赖会违反可信依赖
  激活门禁；因此其职责通过本任务 `spec_refs` 的当前 accepted 规范承接，不把
  TASK-013 的历史交付叙述提升为可信证据。
- TASK-004 本身不得成为 TASK-052 的依赖，否则形成以待 remediation 对象解锁
  remediation task 的循环。

## 2026-08-28 read-only audit

### Repository and governance state

- 审计起点与最新 `origin/main` 均为 PR #88 merge commit
  `bfa77268941f3814d1856c59094fd8a90e3cda81`；PR #88 GitHub 状态为
  `MERGED`，base 为 `main`，4/4 checks successful。
- 开始时 worktree clean、detached Head 精确等于该 merge；`tasks/active/` 仅有
  README，未激活任何任务。
- main、远端 refs、`tasks/active`、`tasks/backlog`、`tasks/completed` 与
  `tasks/index.yaml` 均未发现 TASK-052。远端已存在
  `codex/task-051-risk-validator-scope-successor`，因此本任务使用经授权的
  TASK-052，未占用 TASK-051。
- TASK-004 虽位于 completed 目录，但 delivery 仍为
  `acceptance_status: unverified`、`review_status: reported_unverified`、
  `release_status: prohibited`，PR/Head/reviewer/evidence/merge 均为
  `unverifiable`。目录位置和当前测试结果都不能替代历史 PR/Review 事实。
- TASK-002、TASK-003、TASK-013 同样保留历史 `reported_unverified` 状态；
  本审计只读取其当前代码或规范职责，不把它们当成可信历史 completion evidence。
- 直接依赖 TASK-004 的 backlog tasks 为 TASK-006、TASK-007、TASK-025、
  TASK-027、TASK-048；它们全部继续 blocked。TASK-048 还依赖 TASK-017 与
  TASK-050，但 TASK-004 的不可信 delivery 仍使激活门禁 fail closed。

### Present implementation and evidence inventory

- Application persistence boundary 存在：immutable DTO/Ports、canonical JSON、
  registration fingerprint、Journal/Snapshot checksum、deterministic OMS Outbox
  envelope builders 与 canonical storage/recovery errors。
- Memory adapter 存在：register idempotency、CAS save、Journal chain、Snapshot
  fallback、projection rebuild、recovery pagination、Outbox claim/reclaim/fencing、
  retry/dead-letter 与 critical-lag safety。
- PostgreSQL adapter 存在：基于 `asyncpg` 的有界同步 facade、事务 register/save、
  唯一竞争处理、Journal verification、Snapshot/Recovery、projection rebuild、
  `FOR UPDATE SKIP LOCKED` claim、lease fencing 与 PostgreSQL transaction clock。
- 现有 migration 仅为 `migrations/001_order_persistence_outbox.sql`，创建
  orders/order_journal/order_snapshots/outbox_messages、约束、索引和 Journal
  append-only triggers；文件声明 expand-only 且没有 destructive downgrade。
- 现有 evidence 包含 8 个 application unit tests、13 个 in-memory persistence
  contract tests、2 个 migration/CI contract tests，以及 PostgreSQL integration
  tests 覆盖原子注册、幂等/冲突、CAS/并发竞争、事务 rollback、Journal/Snapshot
  corruption、projection rebuild、recovery enumeration、claim/lease/reclaim、
  retry/dead-letter 与 append-only triggers。
- Runtime dependency 为 optional `storage` extra 中的 `asyncpg`（同时登记
  SQLAlchemy/Alembic）；CI 的 `persistence-postgresql` job 使用 PostgreSQL 16、
  设置 `QUANTIQMT_POSTGRES_DSN` 并执行 persistence unit/contract/integration tests。
- 审计时非 PostgreSQL 基线通过：spec validator；23 个 focused
  unit/contract/migration-contract tests；Mypy；Ruff check/format。该结果只说明
  当前选定测试通过，不是 TASK-004 历史 Review/PR evidence，也不是本任务最终
  revalidation acceptance。
- 本地 `QUANTIQMT_POSTGRES_DSN` 未设置，受限会话无法访问 Docker engine；本轮
  未声称 PostgreSQL integration 已复验。后续必须使用下面的 PostgreSQL 16
  隔离命令或等价、可审计的 CI service，禁止 skip 或用 SQLite/Memory 代替。

### Blocking implementation and evidence gap

- 当前 accepted Spec 0.14（TASK-050）要求 `OrderRegistration` 具有不可变
  `broker` 与 `broker_capability_version`，新 registration 必须 `BOUND`，legacy
  payload 必须在原始 checksum 验证后解析为 `UNBOUND`，projection/replay 必须
  保持同一绑定事实，并要求 expand-only、idempotent 的
  `002_order_registration_broker_capability` migration。
- 当前 `OrderRegistration` DTO、serialization/state payload、Memory/PostgreSQL
  adapter 与 `001` schema 均没有上述绑定字段；仓库不存在 `002` migration，
  现有 persistence tests 也没有 runtime BOUND/UNBOUND、legacy raw-checksum 或
  `002` rollout/rollback 覆盖。这是明确的当前规范/实现/测试缺口，不是单纯的
  历史证据不可验证。
- 该缺口属于 TASK-048 已定义但尚未授权实施的范围，而 TASK-048 又直接依赖
  TASK-004 的可信 delivery。TASK-052 不得利用 waiver、降低 acceptance、修改
  依赖或把旧测试通过冒充解决。人类必须另行授权精确的 remediation 与依赖顺序；
  在此之前 TASK-052 可以保持 active 以记录阻断，但不得进入 passed/approved
  closeout，也不得更新 TASK-004 delivery metadata。

## Revalidation plan

1. 人类先处理上面的 runtime/migration/test 阻断，明确由哪个独立任务实施，以及
   如何解除 TASK-048 ↔ TASK-004 evidence 的顺序问题。TASK-052 本身不修改这些
   文件。
2. remediation 合并后，从最新 `origin/main` 开始新的 revalidation 回合；在
   `ai/governance/task-004-delivery-revalidation-task-052.yaml` 记录 exact base
   main SHA、执行最终校验时的 exact `origin/main` SHA、exact revalidation PR
   number/Head、merge-base、accepted spec baseline、完整 inventory、command/result/
   exit code 与 path audit。Head 变化后全部 acceptance 命令必须重跑。
3. 使用全新 PostgreSQL 16 容器 `quantiqmt-task-052-postgres` 和独立数据库
   `quantiqmt_task052`，显式 DSN 为
   `postgresql://quantiqmt:quantiqmt@localhost:55432/quantiqmt_task052`；确认
   `server_version_num` 位于 `[160000, 170000)`，否则命令非零退出；记录本次
   `docker pull postgres:16` 后 `docker image inspect` 返回的 immutable
   `RepoDigest`。缺少 digest、服务、driver 或 DSN 时 fail closed。
4. 按 `verification.commands` 验证 migration 按文件名顺序重复应用、expand-only
   rollback safety，并显式执行 task-owned migration probe；同时验证
   Order+Journal+Outbox 原子性、幂等/唯一竞争/CAS、Journal chain、Snapshot
   corruption/full replay、projection rebuild、recovery paging、Outbox
   publish-before-ack/reclaim/fencing/retry/dead-letter，以及当前 BOUND/UNBOUND
   compatibility。任何缺少 `002`、DSN 或断言失败均不得改为 skip。
5. 对同一 exact revalidation Head 完成 Mypy、Ruff、治理 validator、完整相关测试
   与 GitHub CI。独立 Review 必须依据 `ai/review/**` 给出正式 `APPROVED`，并绑定
   exact Head、reviewer 与 evidence URL；实现/治理 Agent 不得自批。
6. PR 合并后记录 merge commit。只有 exact Head acceptance、独立 APPROVED Review、
   CI success、merge 与人类 closeout authorization 全部可审计时，后续受控
   closeout 才能运行最终 evidence validator。validator 通过后才能把 TASK-004
   acceptance/review 更新为 `passed`/`approved`，把 completion evidence 指向
   这次新的 revalidation 事实，并迁移 TASK-052 lifecycle。历史不可验证事实仍
   不得被描述成历史 APPROVE。
7. TASK-004 获得新可信 delivery 后只能重新评估 TASK-048 的全部依赖和当前范围；
   TASK-052 不自动激活 TASK-048 或任何下游任务。

## Frozen machine-verification contracts

### Final delivery evidence validator

- 后续实施只能在精确路径
  `scripts/validate_task_052_delivery_evidence.py` 新增最终证据验证器，并在
  `tests/spec/test_task_052_delivery_evidence.py` 为其增加确定性正例及缺字段、
  mismatch、API failure、unmerged、非 exact-Head Review/check-run 等负例。不得
  借此修改通用 validator、放宽 TASK-004/TASK-048 门禁或接受离线 prose 代替
  GitHub 事实。
- 唯一权威输入为
  `ai/governance/task-004-delivery-revalidation-task-052.yaml`、本地 Git objects/
  `origin` remote 与 `--repository qifuxiao/QuantiQmt` 指定仓库的实时 GitHub API。
  artifact 必须至少包含：task/repository、base 与最终 `origin/main` SHA、PR number、
  author、exact Head、merge-base、accepted spec version 及 `spec/manifest.yaml` blob
  SHA-256、每个 exact-Head check-run 的 ID/name/status/conclusion/URL、正式 Review
  ID/URL/reviewer/author association/state/`commit_id`、PR merged state 与 merge
  commit，以及 PostgreSQL image digest/`server_version_num` 和逐命令结果。
- 验证器必须先 fetch `origin/main`，逐项比较 artifact 与本地 Git/GitHub 实时事实：
  记录最终 `origin/main` 的 exact SHA；PR number、author 与 Head；Head 对记录 base
  的 merge-base；merge-base 上 accepted manifest 的 version/status/blob digest；
  exact Head 的所有 check-runs 均为 `COMPLETED/SUCCESS` 且 artifact 未漏记；正式
  Review 为 `APPROVED`、`commit_id` 等于 exact Head、reviewer 不同于 PR author、
  reviewer association 为 `COLLABORATOR`/`MEMBER`/`OWNER` 且 URL/reviewer 一致；
  PR 的实时规范化状态为 `MERGED`、merge commit 与 artifact 一致，并且该 merge
  commit 是最终 `origin/main` 的祖先。
- artifact 缺字段、格式错误、任何值不一致、Git/GitHub API/认证/网络失败、check
  非全绿、Review 非正式或非 exact Head、reviewer 是作者/非 collaborator、PR 未
  merge、merge commit 不可达时，验证器都必须给出非零退出；禁止 warning-only、
  cached response、人工复制的 `git rev-parse` 输出或 activation PR CI 充当通过。

### TASK-052 migration revalidation probe

- 后续实施只可新增
  `tests/integration/persistence/test_task_052_migration_revalidation.py`；这也是唯一从
  原 `tests/integration/**` 禁止范围精确放行的 probe。现有 integration tests 仍
  forbidden，其他 integration 路径也不在 `allowed_paths`。probe 不得实现或修改
  migration/runtime，只消费另行授权并已可信合并的 `001`/`002` artifacts。
- probe 必须在独立 PostgreSQL 16 数据库中先仅应用 `001`，构造含 Order、Journal、
  Snapshot、Outbox 与已记录 raw/canonical checksum 的 legacy 数据；再按顺序应用
  `001 -> 002` 并重复完整序列，断言 schema migration idempotent、既有行与关联链
  全部保留。
- legacy 行不得依据账户、环境或默认值推测 backfill `broker`/
  `broker_capability_version`；读取/恢复时只能在原始 checksum 验证后得到规范定义的
  `UNBOUND`。新 BOUND 数据必须逐轮保持准确的 broker/capability version。迁移前后
  Journal continuity、Snapshot/Outbox payload 与 checksum、registration checksum、
  row counts 和 identity 必须逐项相等或满足规范明确的 expand-only 增量。
- probe 必须注入一次事务内失败并验证失败 rollback 后 schema/data/checksum 与失败
  前完全一致；成功升级后的 operational rollback 只能停止 writer/worker，必须
  保留新增 columns、所有 rows、Journal、Snapshot、Outbox 与 checksums，禁止
  destructive downgrade、DROP、DELETE 或历史覆盖。缺少 `002`、DSN、PostgreSQL
  16、任一 preservation assertion 时必须失败，不得 skip。

## Non-goals

- 不修改 `src/**`、`spec/**`、`migrations/**`、现有业务测试、CI、依赖或 lockfile；
  仅允许后续在上述精确路径新增 task-owned evidence validator/test 与 migration
  revalidation probe。
- 不追溯、猜测、替换或伪造 TASK-004 的历史 PR、Head、Review、CI、merge、
  reviewer 或人类授权。
- 不使用 waiver、completed 目录位置或当前测试全绿绕过可信依赖门禁。
- 不修改或激活 TASK-048，不激活任何其他下游任务。
- 不部署、不发布、不把 release 状态改为 eligible/released。

## Acceptance criteria

- [ ] Revalidation evidence 记录执行时最新 `origin/main` 的 exact SHA、exact PR
  Head 和 accepted spec version；所有命令与独立 Review 均绑定同一 Head。
- [ ] 当前规范与 runtime/migration/test inventory 无未授权缺口；上面记录的
  broker binding/`002` 阻断已由独立、经授权且可信合并的 remediation 解决，
  TASK-052 未修改任何业务、规范或 migration 文件。
- [ ] PostgreSQL 16 隔离环境、`QUANTIQMT_POSTGRES_DSN`、driver、实际 image
  RepoDigest 和强断言通过的 `server_version_num` 均有可审计证据；非 16.x 必须
  非零退出，integration tests 无 skip/sleep/替代存储。
- [ ] 全套 persistence unit、contract、PostgreSQL integration tests 通过，覆盖
  Order+Journal+Outbox 原子提交、幂等/冲突、唯一竞争、CAS、Journal continuity/
  checksum/append-only、Snapshot invalid fallback、full replay、projection rebuild
  与 recovery enumeration。
- [ ] 精确 migration probe 构造 `001` legacy 数据，验证 `001 -> 002` 与重复应用、
  禁止推测 backfill、broker/capability version 语义、Journal/Snapshot/Outbox/
  checksum preservation；事务失败和 operational rollback 后 schema/data 状态保持，
  无 DROP/DELETE/backfill/历史覆盖。
- [ ] Outbox claim/reclaim、publish-before-ack duplicate、same message_id、expired
  token fencing、renew/release/ack、bounded retry、dead-letter 与 critical-lag
  safety acceptance 全部通过。
- [ ] Mypy、Ruff check、Ruff format、spec/governance validator 和精确 path audit
  全部通过，且 revalidation PR 未触及 forbidden paths。
- [ ] 独立 reviewer 对 exact revalidation Head 提交新的正式 `APPROVED` Review；
  reviewer、verdict、evidence URL 与 reviewed Head 可独立核验，非实现者自审。
- [ ] GitHub CI 在 exact reviewed Head 成功，revalidation PR 已合并且 merge commit
  可核验，并取得人类 closeout authorization；最终 evidence validator 对实时 Git/
  GitHub 事实和 evidence artifact 的逐项 fail-closed 比较以退出码 0 完成。
- [ ] 只有上述新证据全部满足后，TASK-004 delivery metadata 才从
  `unverified`/`reported_unverified` 受控更新为 `passed`/`approved`；更新明确
  表示当前 main revalidation，不把历史事实重写为已验证。
- [ ] TASK-048 及所有直接/间接下游任务仍未自动激活；只形成一次新的、独立的
  dependency readiness 重新评估输入。release 继续 prohibited。

## Required evidence

- 使用 `ai/workflows/implement-task.md` 格式记录 task、spec refs、changed files、
  逐项 acceptance、命令/exit code、未验证范围、风险和 spec deviations。
- 记录 `postgres:16` 实际 immutable RepoDigest、强断言通过的
  `server_version_num`、DSN（仅测试凭据）、migration probe 的 legacy fixture、
  顺序与两次应用结果、失败/rollback preservation audit、测试数量与失败/skip 数。
- 记录 exact base/head、PR URL、GitHub CI URLs/conclusions、独立 Review
  verdict/reviewer/evidence URL/reviewed Head、merge commit 和人类 closeout 授权。
- 保存最终 evidence validator 的命令、stdout/stderr、退出码和运行时
  `origin/main` SHA；validator 未以 0 退出时禁止更新 TASK-004 metadata。
- 未能独立复验的事实必须保持 `unverifiable`；不得用 prose 或测试全绿代替
  GitHub Review/merge evidence。

## Review focus

- 区分“历史 evidence 不可验证”和“当前实现不满足当前 accepted spec”；任何一项
  都必须独立 fail closed。
- 核对 Journal/Snapshot 原始 checksum、projection/full replay、Outbox 原子性、
  lease fencing、幂等 identity 与 PostgreSQL 事务边界。
- 核对 TASK-004 metadata 更新只引用新的 revalidation 事实，未制造历史 APPROVE，
  且 TASK-048 仍 blocked、release prohibited。
- 核对 changed paths 只属于 governance evidence、受控 metadata、TASK-052
  lifecycle、精确 validator/test 与 migration probe；不得借 revalidation 修改
  业务实现、migration 或现有业务测试。

## Risks and rollback

- 仅凭旧测试通过可能掩盖当前 Spec 0.14 binding 缺口；因此阻断未解决时不允许
  closeout。
- PostgreSQL/migration/recovery/outbox 任一范围未执行或无法复验时，TASK-004
  保持 unverified，TASK-048 保持 blocked。
- Governance rollback 只恢复 TASK-052 产生的任务投影、evidence artifact 与
  TASK-004 delivery metadata；不得删除或改写 runtime data、Journal、Snapshot、
  Outbox、migration 或历史治理事实。

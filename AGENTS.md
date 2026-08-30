# QuantiQmt Agent Instructions

本仓库由人类与 Codex、Claude Code、Gemini、Cursor 等 AI Agent 协作开发。所有 Agent 必须遵守以下规则。

## 产品交付北极星

- 项目目标是可长期运行的量化交易系统，不是只交付 Python 包、契约集合或 Notebook。
- 当前首要里程碑是 M1：必须连接 Mini QMT，并以精确 allowlist 的模拟资金账号完成
  行情/账户查询和一笔受控模拟委托的端到端闭环。
- Broker Simulator 是确定性测试与故障注入基线，不能替代 M1 的 Mini QMT 验收。
- “尽快可运行”不授权绕过 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution`，
  也不降低 PostgreSQL、审计、UNKNOWN、对账、恢复屏障或 Kill Switch 要求。
- M1 禁止真实资金交易。任何真实资金账号接入、下单或发布必须由独立 task、评审和
  人类明确授权；仅设置环境变量或 profile 不能获得该权限。
- 详细产品目标和 M1 验收分别见
  `docs/00-Architecture/06-Product-North-Star.md` 与
  `docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md`。它们不得覆盖 `spec/`。

## 开始任务前

1. 读取本文件以及目标目录内更近的 `AGENTS.md`（若存在）。
2. 读取 `spec/README.md`、`spec/manifest.yaml`。
3. 只执行 `tasks/active/` 中明确指定的一个任务；没有 active task 时不得自主开始业务开发。
4. 读取任务 `spec_refs` 指向的全部规范并检查依赖任务状态。
5. 检查工作区已有变更，不覆盖或删除不属于当前任务的修改。

## 规范优先级

```text
安全与交易不变量
→ Accepted ADR
→ spec/ 规范性契约
→ 当前 active task
→ 本 AGENTS.md / 子目录 AGENTS.md
→ docs/ 解释性文档
→ Agent 自主判断
```

低优先级内容不得违反高优先级内容。发现冲突必须停止实现并报告，不能自行选择方便的一方。

## 实施边界

- 仅修改 task `allowed_paths`；不得修改 `forbidden_paths`。
- 不得自行新增、删除或改变 Event、Command、DTO、错误码、状态迁移、Repository 或 Workflow 契约。
- 契约确需变化时，先创建规范变更任务，更新 `spec/` 和兼容性说明，经评审后再实现。
- 策略不能导入 Broker、OMS Repository、数据库或 Redis 客户端。
- 禁止绕过 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution` 链路。
- 不确定的外部下单/撤单结果必须进入 UNKNOWN 并对账，禁止盲目重试。
- 不使用 float 处理最终价格、金额、费用和结算。

## 工作方式

- 先写或更新测试，再做满足任务的最小实现。
- 不做任务范围外的重构、依赖升级或格式化全仓库。
- 保持 Domain 纯净，I/O 位于 Port/Adapter 边界。
- 队列、重试、并发、缓存和外部调用必须有界且有 timeout。
- 新增公共行为必须包含日志、指标、错误码和失败路径。
- Mini QMT adapter 必须位于 Port/Adapter 边界；策略不得导入或调用 `xtquant`。
- Mini QMT 默认只读、默认禁止发单、默认 Kill Switch 生效；启动时必须精确校验
  `userdata_mini`、session、account type 和模拟账号 allowlist，任何不确定均 fail-closed。
- Mini QMT 客户端登录凭据不得写入代码、`.env.example`、task、Prompt、fixture、日志或
  Git。通常由已登录客户端提供会话；若券商版本确需 secret，只允许使用受控 secret
  provider，并在 task 中明确验证与脱敏边界。
- 回测运行只能读取版本化、带 checksum 的不可变历史快照；Mini QMT 可作为数据来源，
  但回测运行期间不得读取变化中的实时数据或墙上时钟。
- 回测与模拟实盘共享 Domain、Application、Strategy、OMS、Risk 和 Execution 语义；
  仅 Market、Clock、Scheduler、Broker adapter 等边界实现不同。

## AI 开发指令

- Codex、Cline 与其他 Agent 必须使用同一权威链：本文件 → `spec/manifest.yaml` →
  唯一 active task → 全部 `spec_refs`；工具适配文件不得复制业务契约。
- 用户要求“继续开发”时，先报告当前 active task、依赖状态、允许路径和可演示结果；
  不得以新增治理文档代替已授权的业务实现。
- Task Prompt 必须写明目标、非目标、allowed/forbidden paths、验收、验证命令、失败路径
  和预期演示；可使用 `ai/prompts/miniqmt-m1-task.md` 模板。
- 没有 active 实现 task 时，Agent 只能报告并请求人类激活精确 task，不得自行开始代码。
- Codex-Cline 跨服务器协作遵循四角色边界（详见 `ai/workflows/team-collaboration.md`
  和 `.clinerules/10-codex-handoff.md`）：
  - **Codex**：任务选择、规范/架构设计、Implementation Packet / Repair Packet 和精确
    Head 独立 Review（结论仅 APPROVE、REQUEST_CHANGES 或 BLOCKED）。
  - **Cline**：测试先行、最小实现、验证、commit、push 和 Implementation PR。Cline 必须
    读取 active task 内 Codex Plan；无 active task、Base 不匹配、dirty worktree 或设计
    缺口时 fail-closed（返回 PLAN_BLOCKED），不得自行修改 task/spec 或替代设计。
  - **独立 Codex Review 会话**：只读审查精确 Head；Head 改变后旧 Review 自动失效。
  - **人类**：任务激活、GitHub Approval/merge 和 closeout 授权。
- GitHub commit、branch、PR、CI、Review 和精确 SHA 是跨服务器唯一事实来源，不以聊天
  摘要代替。Implementation PR 与 Closeout PR 必须分离；Cline 不得 self-approve、merge
  或 closeout。

## 完成与证据

完成前必须：

1. 执行 task 中所有 `verification.commands`。
2. 检查每条 acceptance criterion，并记录证据。
3. 报告修改文件、测试结果、未解决风险和规范偏差。
4. 不得自行把任务从 active 移到 completed；由人类或独立 Review Agent 验收后移动。

测试无法执行时不得声称完成，必须说明阻塞原因和未验证范围。

## Review

Review Agent 读取 `ai/review/`，优先检查交易安全、幂等、状态机、恢复、金额精度和越权依赖。发现违反 spec 的实现即为阻断问题，即使测试当前通过。

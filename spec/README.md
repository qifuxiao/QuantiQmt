# QuantiQmt Normative Specifications

`spec/` 是实现层面的唯一技术契约（Single Source of Truth）。`docs/` 解释背景和架构理由；两者冲突时以本目录和最新 Accepted ADR 为准。

## 规范内容

```text
spec/
├── manifest.yaml               # 规范版本和索引
├── invariants/                 # 不可违反的系统不变量
├── contracts/                  # Command/Event/DTO/Error Schema
├── interfaces/                 # Port/API 逻辑签名
├── state-machines/             # 状态、迁移、Guard、Action
├── workflows/                  # 端到端步骤和失败处理
├── repositories/               # 聚合持久化契约
├── storage/                    # Source of Truth 与逻辑 Schema
└── nfr/                        # 性能、可靠性、可观测性
```

## 规范性关键词

- MUST/MUST NOT：强制要求。
- SHOULD/SHOULD NOT：除非 ADR 说明原因，否则必须遵守。
- MAY：可选能力，不得成为其他模块隐式依赖。

## 变更流程

1. 创建独立 spec-change task。
2. 更新机器 Schema、相关规范和 `manifest.yaml` 版本。
3. 描述兼容性、迁移、回滚和受影响任务。
4. 通过人类架构评审。
5. 再创建或解锁实现任务。

禁止实现先行后补规范。已发布字段、状态、错误码和事件名称不得复用为其他含义。

## 与代码的映射

- JSON Schema 是消息字段和类型的规范来源。
- YAML 状态机/Workflow 是允许行为的规范来源。
- Markdown 接口规范定义职责、错误和幂等语义；未来生成的 Python Protocol 必须与之匹配。
- 代码、测试和任务通过 `spec_refs` 引用规范 ID，不复制契约正文。

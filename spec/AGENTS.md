# Specification Agent Instructions

- `spec/` 是规范性契约，不是实现目录。
- 未经 active spec-change task，不得修改本目录。
- 变更必须同步更新 manifest version、兼容性、迁移和受影响 task。
- JSON Schema/YAML 必须保持机器可解析；不得只修改解释文档。
- 禁止为了让现有代码或测试通过而削弱不变量。

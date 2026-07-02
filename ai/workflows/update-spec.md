# Workflow: Change Normative Specification

1. 必须有 active spec-change task 和变更动机。
2. 列出当前契约、提议契约、兼容性和受影响消费者。
3. 更新机器 Schema/YAML、解释、manifest version 和 golden fixture 要求。
4. 定义升级顺序、双读/双写窗口、回滚和删除旧版本条件。
5. 运行 spec/link/schema/task-reference 校验。
6. 人类架构评审通过后才允许创建实现 task。

禁止直接修改已发布 schema 的字段含义；使用新版本。

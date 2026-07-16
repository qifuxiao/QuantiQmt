# Local Development Environment

> Status: Proposed
> 本文只描述本地开发和验证环境，不定义生产部署拓扑。生产数据库、凭证和灾备要求见 [Production-Operations.md](Production-Operations.md)。

## 目标

本地环境必须支持 AI Agent、人类开发者和 Review 会话复现同一组验证命令，尤其是需要真实 PostgreSQL 的 persistence integration tests。没有真实依赖时，不得把相关任务声称为完成。

## Python 与 Poetry

项目使用 Python 3.12 和 Poetry 2.x。优先使用：

```powershell
poetry --version
poetry install --with dev --extras storage
```

如果 Codex/PowerShell 会话找不到 `poetry`，Windows 默认安装路径通常是：

```powershell
& 'C:\Users\Administrator\AppData\Roaming\Python\Scripts\poetry.exe' --version
& 'C:\Users\Administrator\AppData\Roaming\Python\Scripts\poetry.exe' install --with dev --extras storage
```

Review 或开发报告中必须写清楚实际使用的是 `poetry` 还是绝对路径 fallback。

## PostgreSQL 16 测试容器

TASK-004 及后续持久化相关任务要求真实 PostgreSQL。GitHub Actions 使用：

```text
postgres:16
POSTGRES_USER=quantiqmt
POSTGRES_PASSWORD=quantiqmt
POSTGRES_DB=quantiqmt_test
QUANTIQMT_POSTGRES_DSN=postgresql://quantiqmt:quantiqmt@localhost:5432/quantiqmt_test
```

PowerShell 创建容器：

```powershell
docker run -d --name quantiqmt-postgres `
  -e POSTGRES_USER=quantiqmt `
  -e POSTGRES_PASSWORD=quantiqmt `
  -e POSTGRES_DB=quantiqmt_test `
  -p 5432:5432 `
  postgres:16
```

Git Bash 创建容器：

```bash
docker run -d --name quantiqmt-postgres \
  -e POSTGRES_USER=quantiqmt \
  -e POSTGRES_PASSWORD=quantiqmt \
  -e POSTGRES_DB=quantiqmt_test \
  -p 5432:5432 \
  postgres:16
```

如果容器已经存在但停止：

```powershell
docker start quantiqmt-postgres
docker ps
```

如果需要重建本地测试容器：

```powershell
docker rm -f quantiqmt-postgres
docker run -d --name quantiqmt-postgres -e POSTGRES_USER=quantiqmt -e POSTGRES_PASSWORD=quantiqmt -e POSTGRES_DB=quantiqmt_test -p 5432:5432 postgres:16
```

本地测试容器不得保存重要数据。Persistence integration tests 会自动 apply migration，并在测试前清理相关表。

## DSN 环境变量

PowerShell：

```powershell
$env:QUANTIQMT_POSTGRES_DSN="postgresql://quantiqmt:quantiqmt@localhost:5432/quantiqmt_test"
```

Git Bash：

```bash
export QUANTIQMT_POSTGRES_DSN="postgresql://quantiqmt:quantiqmt@localhost:5432/quantiqmt_test"
```

`.env.example` 只提供本地测试示例。真实 Broker 凭证、生产数据库 URL、Token 和密钥不得进入仓库、日志或普通配置文件。

## TASK-004 本地验证示例

```powershell
poetry run pytest tests/unit/order/application tests/contract/persistence tests/integration/persistence
poetry run mypy src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure src/quantiqmt/messaging/outbox
poetry run python scripts/validate_specs.py
poetry run ruff check .
poetry run ruff format --check .
```

若 `poetry` 不在 PATH：

```powershell
& 'C:\Users\Administrator\AppData\Roaming\Python\Scripts\poetry.exe' run pytest tests/unit/order/application tests/contract/persistence tests/integration/persistence
```

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `bash: -e: command not found` | 在 Git Bash 中粘贴了 PowerShell 反引号续行命令 | 使用 Git Bash 的 `\` 续行，或改成单行 `docker run` |
| `QUANTIQMT_POSTGRES_DSN is required` | 当前 shell 未设置 DSN | 按本页设置环境变量后重新运行 pytest |
| `The container name is already in use` | 容器已存在 | `docker start quantiqmt-postgres`，或确认无数据后 `docker rm -f` 重建 |
| `poetry` 找不到 | PATH 未刷新或 Codex shell 隔离 | 使用绝对路径 fallback |
| PostgreSQL integration tests 未运行 | DSN 缺失、容器未启动或依赖未安装 | 不得 APPROVE；先修复环境并重新验证 |

## Review 要求

涉及 PostgreSQL 行为的 Review 必须连接真实 PostgreSQL。仅通过 SQL 文本检查、mock、内存实现或跳过 integration test，不能证明持久化任务完成。

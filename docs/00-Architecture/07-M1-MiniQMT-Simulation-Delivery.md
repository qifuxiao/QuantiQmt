# M1: Mini QMT Simulation-Account Delivery

> Status: Human-approved delivery target (non-normative)
>
> Updated: 2026-08-28
>
> Contract authority: `spec/manifest.yaml` and referenced specifications.

## Required outcome

M1 must connect to the locally installed Mini QMT client and an exact allowlisted 模拟账号.
Broker Simulator 不能替代 M1 的外部验收；它仍是 CI、确定性、错误矩阵与故障注入的必要
基线。M1 does not authorize a real-money account，明确禁止真实资金交易。

The target flow is:

```text
Mini QMT Market/Account
  → MarketGateway
  → Strategy or operator-created OrderIntent
  → OMS registration + PostgreSQL Journal/Outbox
  → Risk
  → OMS transition
  → Execution
  → Mini QMT simulated account
  → normalized order/trade reports
  → OMS + Ledger/Portfolio + audit/reconciliation
```

No component may shorten this path. In particular, a demo script must not call `order_stock` directly
and then assign an OMS final state.

## Runtime profiles

| Profile | Mini QMT | Broker side effect | Purpose |
|---|---|---|---|
| `BACKTEST` | Data may originate from Mini QMT before the run | None | Deterministic immutable replay |
| `MINIQMT_SIM_READONLY` | Required | Forbidden | Connect, subscribe and query |
| `MINIQMT_SIM_TRADING` | Required simulated account | Explicitly gated | End-to-end simulated trading |
| `LIVE_PROHIBITED` | Irrelevant | Forbidden | Fail-closed placeholder, not a release mode |

Profile selection is not authorization. Order dispatch additionally requires the exact account
allowlist, verified capability binding, closed uncertainty set, disabled Kill Switch, explicit
`ORDER_SEND_ENABLED=true`, hard limits and an open recovery barrier. A value resembling `LIVE` must
be rejected while no separately reviewed real-money task and release approval exist.

## Mini QMT connection contract for M1

The operator logs into the Mini QMT desktop client. The adapter receives the local `userdata_mini`
path, a unique integer session ID, account ID and account type. The repository must not ask an Agent
or developer to paste the Mini QMT password into a Prompt, task, fixture or tracked file.

Startup is fail-closed and must verify, with bounded deadlines:

1. The runtime is Windows and the task-approved `xtquant` version imports successfully.
2. `userdata_mini` exists and belongs to the intended Mini QMT installation.
3. The client is running and connected; `connect()` succeeds.
4. Subscription/query succeeds for the exact configured account and account type.
5. The configured account is present in `ALLOWED_ACCOUNT_IDS`; ambiguous environment identity fails.
6. Broker capabilities and version are bound to each new OrderRegistration before persistence.
7. Read-only mode cannot reach submit/cancel methods even if caller input is malformed.

The current project requires Python 3.12 while deployed xtquant builds may have narrower support.
The first implementation task must test the installed wheel and client in read-only mode. It may not
silently change the repository Python baseline, download an unreviewed binary or send an order.

External implementation references are the official ThinkTrader
[XtQuantTrader API](https://dict.thinktrader.net/nativeApi/xttrader.html),
[quick start](https://dict.thinktrader.net/nativeApi/start_now.html?id=dqamF2) and
[connection troubleshooting](https://dict.thinktrader.net/nativeApi/question_function.html?id=TB5IbM).
They describe vendor mechanics but do not override repository contracts or safety gates.

## Configuration boundary

`.env.example` contains names and safe defaults only. Local `.env` is ignored by Git. Mini QMT desktop
login is preferred; if a specific broker build demonstrably requires an application secret, the task
must use a controlled secret provider such as the operating-system credential store. Secrets and raw
account identifiers must be redacted from logs and forbidden as metric labels.

Trading defaults are:

- `PROFILE=MINIQMT_SIM_READONLY`
- `ORDER_SEND_ENABLED=false`
- `KILL_SWITCH_ENGAGED=true`
- no account allowlist entry
- bounded order notional and explicit instrument allowlist

Changing to `MINIQMT_SIM_TRADING` is a two-step operator action and still cannot bypass runtime gates.

## Backtest/live semantic parity

Mini QMT may download or export historical data before a backtest. Ingestion validates and freezes a
不可变 dataset manifest, partitions, calendar, adjustment policy, recorded availability and checksum. 回测
运行期间, adapters read only that immutable snapshot; they do not query changing Mini QMT data,
wall-clock time or ambient randomness.

Backtest and simulated live share Strategy artifacts, OrderIntent validation, Target resolution, OMS,
Risk, Execution request contracts, Ledger/Portfolio rules and audit shapes. Backtest replaces only
Market, Broker, Clock and Scheduler adapters with Historical Market, Execution Simulator,
VirtualClock and deterministic scheduling. It models latency, fees, liquidity and failures explicitly;
it does not claim identical external outcomes.

## Acceptance scenarios

1. Read-only probe reports client/API version, sanitized path identity, session, account type,
   connection and subscription/query outcomes without logging secrets or raw account metrics.
2. The system queries simulated account funds, positions, open orders and trades with bounded timeout.
3. With explicit gates opened, one minimum-size allowlisted OrderIntent traverses the complete path and
   produces persisted registration, Risk evidence, execution attempt and normalized Broker reports.
4. A Risk rejection is auditable and produces zero Mini QMT submit calls.
5. Replaying the same intent/idempotency identity produces no duplicate external order.
6. Submit timeout or disconnect after possible dispatch becomes UNKNOWN, blocks unsafe progress and is
   resolved by same-identity query/reconciliation without blind retry.
7. Duplicate and out-of-order callbacks remain idempotent; only OMS changes business order state.
8. Process restart begins SAFE, restores PostgreSQL facts, queries Mini QMT, reconciles and requires the
   recovery gate before accepting new intents.
9. A deterministic backtest consumes an immutable checksum-bound snapshot under VirtualClock twice
   and produces byte-identical business trace/checksums for identical inputs.
10. A correlation-linked report shows strategy decision, OrderIntent, registration, Risk rule results,
    OMS transitions, execution attempts, Broker reports, trades and operator actions.

## Target operator interface

The following commands are a target interface, not a claim that the current repository implements them:

```powershell
poetry run quantiqmt probe miniqmt --profile MINIQMT_SIM_READONLY
poetry run quantiqmt run --profile MINIQMT_SIM_READONLY
poetry run quantiqmt run --profile MINIQMT_SIM_TRADING
poetry run quantiqmt backtest --dataset <immutable-dataset-id>
poetry run quantiqmt audit order --correlation-id <id>
```

Each implementation task that adds one command must include success/failure tests, bounded timeouts,
structured audit evidence, an operator-visible demonstration and exact verification commands.

## Non-goals and release boundary

- No real-money account, limited live or production trading.
- No automatic GUI credential entry or password storage in the repository.
- No strategy-to-xtquant shortcut, direct SQL state repair or external side effect before persistence.
- No claim that backtest profits predict simulated or real performance.
- No release based only on documentation, unit tests or a successful socket connection.

M1 is complete only after its implementation tasks are independently reviewed, merged and demonstrated
against the designated Mini QMT simulated account. This document alone does not complete M1.

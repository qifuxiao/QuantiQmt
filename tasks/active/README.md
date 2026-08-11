# Active Tasks

- TASK-020: 当前唯一 active task。

TASK-020 仅用于冻结 Market data 与 MarketGateway L4 contracts；不连接 MiniQMT，不实现 runtime 或 migration，不授权发布或自动解锁任何下游任务。

TASK-022 保持 backlog/ready、尚未激活；TASK-021、TASK-023 以及其他 blocked task 保持 blocked。其他任务状态不变。

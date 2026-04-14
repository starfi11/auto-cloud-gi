# Auto-Cloud-GI 重构蓝图（唯一文档）

## 1. 当前内核目标

项目定位为通用 GUI 自动化控制系统（不绑定原神），核心运行循环：

1. `sense`（感知）
2. `decide`（决策）
3. `act`（执行）
4. `verify`（验证）

并且要求可跨软件上下文切换（云原神、bettergi、QQ 等）。

## 2. 已落地核心能力（本次）

### 2.1 分层状态机

当前 `RunContext` 已具备三层运行态：

1. `global_layer`：全局流程状态
2. `context_layer`：当前活跃界面上下文（可切换）
3. `controller_layer`：当前控制单元与动作结果

相关实现：

- `src/domain/layered_state.py`
- `src/kernel/context_store.py`
- `src/kernel/context_manager.py`
- `src/app/run_executor.py`

### 2.2 感知不确定性一等公民

新增感知模型：

- `PerceptionCandidate`（候选 + 置信度）
- `PerceptionResult`（候选集合 + 不确定性原因 + 证据引用）

`StateEstimate` 已支持携带 perception 与 uncertainty。策略层对低置信度会优先等待，不盲动。

相关实现：

- `src/domain/perception.py`
- `src/domain/state_kernel.py`
- `src/ports/perception_port.py`
- `src/ports/vision_port.py`
- `src/adapters/policy/table_policy_engine.py`

### 2.3 统一恢复矩阵（异常->恢复）

执行失败不再只靠动作私逻辑，统一走 `RecoveryStrategy`：

- `retry`
- `switch_context_then_retry`
- `fail`
- `escalate`

默认已接入 `TableRecoveryStrategy`。

相关实现：

- `src/domain/recovery.py`
- `src/ports/recovery_strategy_port.py`
- `src/adapters/recovery/table_recovery_strategy.py`
- `src/app/run_executor.py`

### 2.4 可回放事件序列

运行日志新增 `seq` 单调序号，支持跨 events/transitions/actions 的统一时间线回放。

相关实现：

- `src/infra/log_manager.py`
- `src/infra/run_replay.py`

### 2.5 资源仲裁模型

新增 `ResourceArbiter` 资源租约模型，支持动作声明并申请 `mouse/keyboard/focus` 等共享资源。

相关实现：

- `src/kernel/resource_arbiter.py`
- `src/app/run_executor.py`

## 3. AI 扩展缺口（预留位）

AI 不接管主流程，只作为异常兜底规划器：

- 新增 `AiRecoveryPlannerPort`
- 仅在 `RecoveryDirective=escalate` 时触发
- 产出建议并记录，后续可接入安全闸再执行

相关实现：

- `src/ports/ai_recovery_planner_port.py`
- `src/adapters/recovery/noop_ai_recovery_planner.py`
- `src/app/run_executor.py`

## 4. 当前仍待完善

1. 真实视觉识别适配（OCR/模板匹配）尚未接入，仅有端口与模型。
2. `ContextManager.switch_to` 目前为逻辑切换，尚未绑定真实窗口焦点验证（需要 WindowPort）。
3. AI 建议目前只记录不执行，后续需接 `SafetyGate` 与动作白名单。
4. replay 目前基于日志回放，后续可进化为完整 event-sourcing 快照重建。

## 5. 设计结论

当前架构已完成从“脚本执行器”到“可扩展自动化内核”的关键跃迁：

- 状态驱动 + 上下文切换 + 控制器解耦
- 异常恢复统一化
- 可观测与回放可追因
- AI 能力可插拔但被约束在安全边界内


## 6. 调试三件套（新增）

### 6.1 证据链

`state_estimated` 与 `action_result` 已支持 `evidence_refs` 字段（截图路径等）。

### 6.2 决策可解释

`policy_decision` 已写入 `explain` 字段，记录决策类型、规则理由、是否有动作。

### 6.3 最小确定性回放

新增 `replay_trace.jsonl`，执行器会写 `sense/decision/transition/action_result` 轨迹。
可通过 `src/infra/run_replay.py` 的 `replay_state_transitions(log_root, run_id)` 校验状态迁移链是否一致。

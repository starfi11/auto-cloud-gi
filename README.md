# auto-cloud-gi

## 项目定位

这是一个正在重构中的**Python 自动化控制系统**，用于云游戏场景的任务编排。

当前设计目标：

- 事件驱动执行（非固定 sleep）
- Action 子类建模（业务动作）
- 运行时适配器解耦（实现策略）
- 结构化日志与可中断运行

> 重要：项目已移除 AHK/BAT 依赖路线，后续识别/点击统一走 Python 库能力。

## 重构文档

- `docs/rebuild-blueprint.md`
- `docs/rebuild-todo.md`

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m src.app.bootstrap
```

Windows / PowerShell 可直接用一条 Python 命令发起烟测，避免手写 `Invoke-RestMethod`：

```powershell
python .\scripts\smoke_run.py --wait
```

仅创建 run（不等待）：

```powershell
python .\scripts\smoke_run.py
```

跟踪已有 run：

```powershell
python .\scripts\smoke_run.py --run-id <run_id>
```

先做运行时依赖自检（推荐）：

```bash
python scripts/check_runtime_deps.py
```

默认 OCR 引擎为 `PaddleOCR`（`OCR_ENGINE=paddle`）。

若切换到 `tesseract`，请安装 Tesseract OCR，并在 `.env` 配置：

```env
OCR_ENGINE=tesseract
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANG=chi_sim+eng
```

## 配置说明

使用 `.env` 配置运行参数，核心项：

- `AUTOMATION_DEFAULT_PROFILE=genshin_cloud_bettergi`
- `GAME_RUNTIME_MODE=python_native`
- `ASSISTANT_RUNTIME_MODE=python_native`
- `COMMAND_SOURCE_FILE=./runtime/commands/inbox.json`

当前启用 profile：

- `genshin_cloud_bettergi`：云原神 + BetterGI

## 控制接口

- `POST /api/v1/runs`
- `POST /api/v1/runs/dry-run`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/runs/{run_id}/interrupt`
- `POST /api/v1/runs/{run_id}/risk`

示例：

```bash
curl -X POST http://127.0.0.1:8788/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "trigger": "API_TRIGGER",
    "idempotency_key": "demo-001",
    "target_profile": "genshin_cloud_bettergi",
    "scenario": "daily_default",
    "requested_policy_override": {}
  }'
```

其他 profile 作为扩展位保留，不在当前默认运行集内。

## 当前状态

已完成：

- 核心编排骨架（Orchestrator / RunExecutor / State）
- Action 子类分发与执行
- 运行中断与风险抢占
- 幂等与运行记录持久化
- 结构化日志（system/control-api/run）

待完成：

- Python-native 识别与点击的真实实现
- 场景判定多信号融合（OCR/图标/窗口状态）
- 云端调度闭环（SchedulerPort 生产实现）

## v2 迁移适配参数（RunRequest.overrides）

可通过 `requested_policy_override` 调整云原神/BetterGI行为：

- `queue_strategy`: `normal|quick|none`
- `assistant_log_root`: BetterGI 日志目录
- `assistant_log_glob`: 日志匹配（如 `better-genshin-impact*.log`）
- `assistant_idle_seconds`: 日志静默多久视为完成
- `assistant_timeout_seconds`: 最长等待时间
- `assistant_require_log_activity`: 是否要求先观察到日志增长

其中 BetterGI 完成判定采用通用“日志活动监听器”而非硬编码 BetterGI 逻辑。

## 视觉资源与信号目录约定

- 文本信号文件：`runtime/vision/signals/latest.txt`
- 图标模板根目录：`runtime/vision/templates`
- UI 元素定义：`runtime/vision/elements.json`

建议模板组织方式：

- `runtime/vision/templates/genshin_cloud_bettergi/*.png`
- `runtime/vision/templates/<profile_name>/*.png`

当前已接入“文本信号等待”用于 `wait_game_ready`：

- `scene_ready_text_any`
- `scene_block_text_any`
- `text_signal_file`

图标出现/消失检测接口与模板目录已预留，具体匹配逻辑可在你准备好模板后接入。

## UI Element（文本优先，模板兜底）

动作层支持 `click_element / wait_element`。解析策略：

1. 先按 ROI 做 OCR 文本匹配（低开销）。
2. ROI 失败后自动扩圈。
3. 仍失败则全局模板匹配兜底。

默认元素定义文件：`runtime/vision/elements.json`，可通过环境变量覆盖：

- `VISION_ELEMENT_SPEC`
- `VISION_TEMPLATE_ROOT`

OCR 引擎默认使用 `PaddleOCR`，可通过 `OCR_ENGINE` 切换为 `tesseract` 或 `none`。

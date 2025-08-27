# 基于 BetterGI 的云端自动日活托管

## 🧩 项目简介

本项目旨在构建一个稳定可用的**云游戏自动托管方案**，结合：

- 🟡 **BetterGI**
- ☁️ **按量计费 ECS 云服务器**
- 🎮 **云端客户端**
- 🧠 **AHK 自动点击脚本 + 一条龙任务启动**
- 📊 **AI 自动分析日志，判断日活是否完成**
- 🤖 **企业微信机器人发送日志反馈**

实现**无需人工操作的自动化执行 + 日志分析与推送**。

部署好的本方案大概表现为：每天固定时间点 ECS 自动开机并执行自动化任务，自动化任务启动云游戏，根据选定的排队策略进行排队，直到进入游戏后启动 BetterGI ，设置捕获窗口为云游戏窗口，然后启动 BetterGI 一条龙，最后将当天的 BetterGI 的日志与分析结果通过企业微信机器人推送，随后 ECS 到点自动关机。

---

## 📌 项目结构

| 文件名                    | 功能说明                                                  |
| ------------------------- | --------------------------------------------------------- |
| `auto-cloud-GI.bat`       | 自动化任务：启动云游戏 + 排队点击 + BetterGI + 一条龙执行 |
| `enter_genshin_queue.ahk` | 自动点击“开始游戏”并进入排队的一系列针对不同情况的 AHK    |
| `change_btgi_window.ahk`  | 控制 BetterGI 手动选择截图窗口并启动“一条龙”的 AHK        |
| `send_wecom_log.bat`      | 上传当日 BetterGI 日志到企业微信机器人的 BAT              |
| `my_log.txt`              | 生成的运行日志                                            |
| wait_until_enter.ahk      | 由轮询像素点实现的等待云游戏排队的阻塞 BAT                |
| `load_config.ahk`         | 将配置导入 AHK 中                                         |
| `enter_door.ahk`          | 点击进门                                                  |
| `config_example.ini`      | 配置示例文件                                              |
| `auto-cloud-gi-task.xml`  | 注册任务的 XML                                            |
| `bgi_ai_summary.ps1`      | 调用大模型分析当天的 bettergi 日志并推送企业微信          |

---

## 📦 系统配置要求

**本脚本适用于以下环境（其他环境请自行适配）**：

- 云主机：阿里云 ECS `ecs.sgn8ia-m2.xlarge`（搭载 GPU）
- 操作系统：Windows Server（推荐 Server 2019+）
- 云游戏客户端：PC版
- BetterGI：最新版本
- 显示驱动：已正确安装 NVIDIA GRID 驱动、虚拟显示器驱动
- VNC 环境：已部署 TightVNC Server 以绕开 RDP 键鼠输入限制

---

## 🚀 使用步骤

### 1️⃣ 云主机准备

- 使用阿里云 ECS 创建带 GPU 的实例（如 `ecs.sgn8ia-m2.xlarge`）

---

### 2️⃣ 安装基础依赖

#### ✅ 安装显卡驱动（使用阿里云“云助手”执行）

```powershell
$InstalledPlugins = $(acs-plugin-manager --list --local)
if ($($InstalledPlugins | Select-String "gpu_grid_driver_install")) {
  acs-plugin-manager --remove --plugin gpu_grid_driver_install
}
acs-plugin-manager --fetchTimeout 0 --exec --plugin gpu_grid_driver_install
```

#### ✅ 安装 AHK

#### ✅ 安装 pwsh

---

### 3️⃣ 安装 VNC 和虚拟显示器驱动

#### ❗ 重要：不要使用 RDP（远程桌面）执行脚本

- 原因：RDP 可能导致鼠标输入异常，影响游戏和 BetterGI 控制

#### ✅ 安装 TightVNC

- 本地安装 Viewer
- 远程服务器安装 Server 并配置开机自启、无密码登录

#### ✅ 安装虚拟显示器驱动（Spacedesk）

```powershell
winget install --id=Datronicsoft.SpacedeskDriver.Server -e
```

然后进入系统的**显示设置**：

- 设置“虚拟显示器（NVIDIA）”为主显示器
- 或者设置“仅在该显示器上显示”
- 分辨率调整为 `1920x1080`

---

### 4️⃣ 配置企业微信机器人（日志推送）

- 在企业微信群添加自定义机器人
- 拿到 Webhook URL，填入 `send_wecom_log.bat` 中对应变量（`HOOK_KEY`）

---

### 5️⃣ 填写路径配置（在 `config.ini` 中）

根据实际路径修改以下项：

```bat
set BTGI_DIR=...
set GI_EXE=...
set AHK_SCRIPT_QUEUE=...
set AHK_SCRIPT_BTGI=...
set BAT_SEND_LOG=...
```

---

### 6️⃣ 设置自动启动

- 使用 **Windows 任务计划程序** 配合提供的 `auto-cloud-gi-task.xml` 文件来设置自动启动
- Win + R → `taskschd.msc`，使用 XML 文件导入任务

---

### 7️⃣ 配置 AI 日志分析

- 支持通过 **大模型 API** 自动分析日志，判断每日任务是否完成  
- 默认使用 Qwen Turbo 模型
- 需要在 `config.ini` 中填写以下字段：  
  ```ini
  AI_BASE_URL=https://dashscope.aliyuncs.com/compatible/v1
  AI_MODEL=qwen-turbo
  AI_API_KEY=sk-xxxxxx
  ```

## 🛠 已知问题 / 注意事项

- 不支持远程桌面（RDP）环境下运行云游戏 + BetterGI 脚本
- AHK 脚本的模拟点击坐标在 Y 坐标上都做了一个偏移，具体原因不清楚，但这样做了之后在上面描述的环境中才能够按预期运行
- 脚本中使用了屏幕坐标点击，如 ECS 分辨率或比例不一致，可能需要适配 Y 偏移
- 在VNC连接情况下手动执行自动脚本尝试在云游戏上执行一条龙可能不会顺利地执行，画面也会很卡顿，但在无连接情况下执行是正常的
- 企业微信机器人日志推送只支持文件大小在 20MB 以下
- 所有脚本需以管理员身份运行
- 避免为入口 BAT 配置了复数个启动自动执行，这会导致执行异常
- 保证自动化执行是在操作系统启动稳定后（XML中已配置延迟执行）
- 建议在合适的时间定时执行

---

## 💬 声明

> 本项目仅供 **个人学习与研究自动化技术** 使用。
>
> 不涉及任何账号信息，不修改或绕过任何第三方系统机制，不用于生产环境。
>
> 所有风险由使用者自行承担，作者不对任何使用结果负责。

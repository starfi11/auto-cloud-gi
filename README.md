# README

## 项目简介

本项目旨在构建一个稳定可用的**云游戏自动托管方案**，结合：

- **BetterGI**
- **按量计费 ECS 云服务器**
- **云游戏客户端**
- **AHK 自动点击脚本 + 一条龙任务启动**
- **AI 自动分析日志，判断日活是否完成**
- **企业微信机器人发送日志反馈**
- 依赖**云函数FC** + **WorkFlow** 的整体重试

实现可靠的**无需人工操作的自动化定时游戏日活执行 + 日志分析与推送**。

部署好的本方案大概表现为：每天固定时间点 ECS 自动开机并执行自动化任务，自动化任务启动云游戏，根据选定的排队策略进行排队，直到进入游戏后启动 BetterGI ，执行日活（设置捕获窗口为云游戏窗口，然后启动 BetterGI 一条龙），最后将当天的 BetterGI 的日志与分析结果通过企业微信机器人推送，随后 ECS 到点自动关机。

项目提供简易的重试机制保证发生普通异常情况（如一条龙委托领取时未识别到橙色区域导致委托奖励领取失败）时，也能依靠外部重试保证当天最终日活一定无遗漏完成。但项目目前使用的技术栈是脚本，预计基于opencv重构后支持一些特殊异常情况的处理（云游戏更新、btgi更新、云游戏网络波动导致掉线）

项目也支持执行过程截图上云，排查问题较为方便。

## 项目结构

| 文件名                   | 功能说明                    |
| ------------------------ | --------------------------- |
| `auto-cloud-GI.bat`      | 任务入口                    |
| `config_example.ini`     | 配置示例                    |
| `auto-cloud-gi-task.xml` | 注册任务的 XML              |
| `/log`                   | 执行日志、过程截图          |
| `/ahk`                   | 点击脚本                    |
| `/utils`                 | 功能脚本                    |
| `/optional`              | 扩展功能的外部使用配置/代码 |

---

## 系统配置要求

**本脚本适用于以下环境（其他环境请自行适配）**：

- 云主机：阿里云 ECS `ecs.sgn8ia-m2.xlarge`（搭载 GPU）
- 操作系统：Windows Server（推荐 Server 2019+）
- 云游戏客户端：PC版
- BetterGI：最新版本
- 显示驱动：已正确安装 NVIDIA GRID 驱动、虚拟显示器驱动
- VNC 环境：已部署 TightVNC Server 以绕开 RDP 键鼠输入限制

---

## 使用步骤

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
- 远程服务器安装 Server

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
- 通过配置注册表项 `AutoAdminLogon=1`，并设置 `DefaultUserName` 与 `DefaultPassword`，实现系统启动后自动跳过登录界面并直接进入桌面

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

### 8️⃣ 配置 bettergi

- 手动将BETTERGI的截图器切换为windowsgraphicscapture
- 根据需要修改一条龙配置

## 已知问题 / 注意事项

- 不支持远程桌面（RDP）环境下运行云游戏 + BetterGI 脚本
- 分辨率需为 1920*1080
- 在VNC连接情况下手动执行自动脚本尝试在云游戏上执行一条龙**可能**不会顺利地执行，画面也会很卡顿，但在无连接情况下执行是正常的
- 企业微信机器人日志推送只支持文件大小在 20MB 以下
- 所有脚本需以管理员身份运行
- **避免**为入口 BAT 配置了复数个启动自动执行，这会导致执行异常
- 保证自动化执行是在操作系统启动稳定后（XML中**已配置延迟执行**）
- 建议在合适的时间定时执行
- 建议选取合适的区域领取委托奖励

---

## 扩展功能

在 `config.ini` 中，有这样复数个扩展功能。

```bash
[Features]
; 功能开关 ( true/false ) 决定是否启用对应功能，布尔值后面不要加注释/空格
; 启用屏幕取样功能
Enable_ScreenSampler=false
; 启用企业微信日志推送功能
Enable_WeComLog=true
; 启用AI日志分析功能
Enable_AI_Summary=true
; 启用网盘上传屏幕采样功能
Enable_QuarkUpload=false
; 启用云函数重试功能，在AI日志分析结果为失败时触发云函数重试
Enable_FcRetry=false
; 云游戏排队策略： 普通排队、快速排队、云游戏会员队列
Queue_Strategy=enter_genshin_queue.ahk
```

下面展示功能间的依赖关系，开启上级功能时需要同时开启其依赖功能。

```
屏幕取样-->网盘上传
AI日志分析-->云函数重试
```

下面详细讲解各个功能的配置和使用方法

### 企业微信日志推送

```
HOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxxxxxx
HOOK_KEY=xxxxxxxxxxxx
LOG_DIR=C:\Program Files\BetterGI\log
```

### AI日志分析

```
[AI]
; 百炼Key
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-turbo
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
; 可选：分析日志的末尾行数（不配则默认600）
AI_TAIL=600
```

### 屏幕采样与网盘上传

屏幕采样将开关置为true即可，网盘上传目前依赖这样的逻辑：提前在浏览器中登录好网盘账号，并进行一次上传，上传在log/screens文件夹下的某个文件。

通过最开始的这一次上传，后续每次在网页端中点击上传时，打开的都会是log/screens的文件目录，此时，程序会保证每次上传时log/screens目录里只有日期为名称的文件夹及其压缩包。通过这样固定的点击完成每天的上传。

### FC & WorkFlow重试

需要将optional/gi-retry中的`index.js`部署为云函数，`auto-cloud-gi-workflow`部署为workflow，`env_example.json`作为FC的环境变量配置。

需要注意的是，还需要为gi-retry这一功能申请一个权限策略，创建两个角色，分别绑定到workflow和fc上。权限策略分别为fc：启动workflow、表格存储读写；workflow：ECS启动、节省关闭。

主要在做这样的事：每天的执行结果（AI分析结果）会发送到云函数处，云函数接收后执行，如果内容为运行异常，则尝试执行调workflow执行重试逻辑，否则结束。云函数在表格存储中维护了上次重试时间与上次重试当天的总重试次数，以保证每天重试次数不超过指定次数。满足条件时，云函数会调workflow让其去做重试逻辑，然后结束云函数生命周期。

比较麻烦是权限策略配置、角色创建、相关服务开通，相关配置后续补上。



## 声明

> 本项目仅供 **个人学习与研究自动化技术** 使用。
>
> 不涉及任何账号信息，不修改或绕过任何第三方系统机制，不用于生产环境。
>
> 所有风险由使用者自行承担，作者不对任何使用结果负责。

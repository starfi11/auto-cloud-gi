param(
  # 允许从 BAT 传，也可不传（不传则用 $env:LOG_FILE）
  [string]$LogPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# ===== 读取环境变量（由 config.ini 注入）=====
$BaseUrl = $env:AI_BASE_URL
$Model   = $env:AI_MODEL
$ApiKey  = $env:AI_API_KEY
$HookKey = $env:HOOK_KEY           
$Tail    = [int]($env:AI_TAIL)     # 可选行数；未设置时为 600
if ($Tail -le 0) { $Tail = 600 }

# Webhook：优先用 WECOM_WEBHOOK，其次用 HOOK_KEY 组装
$Webhook = $env:WECOM_WEBHOOK
if ([string]::IsNullOrWhiteSpace($Webhook)) {
  if ([string]::IsNullOrWhiteSpace($HookKey)) {
    throw "未发现 WECOM_WEBHOOK 或 HOOK_KEY，用于企业微信机器人地址。"
  }
  $Webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=$HookKey"
}

# 日志路径：入参优先，其次用 $env:LOG_FILE
if ([string]::IsNullOrWhiteSpace($LogPath)) { $LogPath = $env:LOG_FILE }
if (-not (Test-Path -LiteralPath $LogPath)) {
  throw "找不到日志文件：$LogPath"
}

# 基础校验
if ([string]::IsNullOrWhiteSpace($BaseUrl) -or
    [string]::IsNullOrWhiteSpace($Model)   -or
    [string]::IsNullOrWhiteSpace($ApiKey)) {
  throw "AI_BASE_URL / AI_MODEL / AI_API_KEY 未配置完整。"
}

# ===== 1) 取日志尾部 N 行 =====
$tailText = (Get-Content -LiteralPath $LogPath -Encoding UTF8 -Tail $Tail) -join "`n"

# ===== 2) 提示词（稳定模板，避免“预训练对话”依赖）=====
$sys = @'
你是 BetterGI（日常自动化游戏日活）日志分析助手。BetterGI 用于自动执行一条龙（日活）：识别队伍→传送→到点→交互/战斗→领奖/每日委托。你的任务是基于运行日志判断每次自动执行是否成功，并给出判断依据。

【分段规则（以时间戳为准，连续时间段切分）】
- 按行扫描日志，遇到“相邻两行时间戳间隔 ≥ 120 秒”即切分为新的一段；否则视为同一段连续执行。
- “→ 任务启动！”/“任务结束”仅作辅助提示，不强制分段；跨日必定切分；最后一段若无“任务结束”，以末行时间为段结束。
- 仅输出最近 8 段。

【每段输出一行（纯文本、不要JSON/代码块/标题），字段用全角竖线分隔】
[开始HH:MM:SS–结束HH:MM:SS] 运行：<正常/异常> ｜ 委托：<已领取/未领取/不涉及> ｜ 因：<16字内主要原因> ｜ 证：<2–3个关键原文短语>

【运行=正常 的判断】
- 段内出现关键成功信号：如“识别到的队伍角色”“传送完成，返回主界面”“到达路径点附近/精确接近目标点”“结束/完成/战斗完成”等，且无后续致命错误；或虽有 WARN/重试但最终出现成功信号。

【运行=异常 的常见要因（择一写入“因”并在“证”给出短证据）】
- 队伍识别失败/置信度极低（例：“无法识别第1位角色…置信度0.x”“队伍角色识别失败”）
- 地图/传送失败（例：“打开大地图失败”“传送失败”“未处于大地图界面”）
- 对话/交互失败（例：“未进入…交互对话界面”“与凯瑟琳对话失败”“未找到…按钮/图标”）
- 资源/配置不匹配（例：“自动秘境…可用树脂无法满足配置”）
- 焦点/遮挡/UI比例问题（可据日志症状归因）

【每日委托（只在该段涉及时判定）】
- 若出现“每日委托/前往冒险家协会领取奖励/委托按钮/历练点/凯瑟琳”等：
  - 见到领取成功/已领取/完成等明确信号 → “已领取”
  - 仅见打不开冒险之证/未找到委托按钮/对话失败等 → “未领取”
- 未涉及该流程 → “不涉及”

【输出示例（仅示意，不要额外解释或多余行，但如果运行异常，可以用简短的一句话说明你观察到的异常现象和你理解的可能原因是什么）】
[07:03:54–07:04:16] 运行：异常 ｜ 委托：不涉及 ｜ 因：队伍识别失败 ｜ 证：‘置信度0.2’、‘队伍角色识别失败’、‘未进入…对话’
[09:03:46–09:04:23] 运行：正常 ｜ 委托：不涉及 ｜ 因：识别队伍+传送完成 ｜ 证：‘识别到的队伍角色’、‘传送完成，返回主界面’

要求：仅输出上述每段的一行列表；不要标题、不要总结；“因”精炼至≈16字，“证”直接摘抄2–3个关键原文短语。
'@

$user = "以下是BetterGI日志末尾${Tail}行：`n`n$tailText"

$body = @{
  model = $Model
  messages = @(
    @{ role='system'; content=$sys },
    @{ role='user';   content=$user }
  )
  temperature = 0
  seed = 7  # 固定种子，增强稳定复现
} | ConvertTo-Json -Depth 12

# ===== 3) 调用通义千问（OpenAI 兼容 /chat/completions）=====
try {
  $resp = Invoke-RestMethod -Method Post -Uri ("{0}/chat/completions" -f $BaseUrl) `
            -Headers @{ Authorization = "Bearer $ApiKey" } `
            -ContentType 'application/json; charset=utf-8' `
            -Body $body
  $summary = ($resp.choices[0].message.content | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($summary)) { $summary = 'AI分析失败：返回为空' }
}
catch {
  $summary = "AI分析失败：" + ($_.Exception.Message)
}

# 企微 text 消息有大小限制，这里留些余量
$maxLen = 1800
if ($summary.Length -gt $maxLen) { $summary = $summary.Substring(0, $maxLen) + '…' }

# ===== 4) 发企业微信文本 =====
$wx = @{ msgtype='text'; text=@{ content = $summary } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri $Webhook -Method Post -Body $wx -ContentType 'application/json; charset=utf-8'

Write-Host "[OK] 已发送AI简报到企业微信"

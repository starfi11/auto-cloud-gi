param(
  [string]$LogPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# ========== 读取 config.ini 到进程环境 ==========
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configPath = Join-Path $ScriptDir 'config.ini'
if (-not (Test-Path $configPath)) { throw "未找到配置文件：$configPath" }

Get-Content $configPath -Encoding UTF8 | ForEach-Object {
  $line = $_.Trim()
  if ($line -match '^\s*;') { return }
  if ($line -match '^\s*\[.*\]') { return }
  if ($line -match '^\s*([^=]+?)\s*=\s*(.*)$') {
    $k = $matches[1].Trim()
    $v = $matches[2].Trim().Trim('"').Trim("'")
    if ($k -and $v) { [Environment]::SetEnvironmentVariable($k, $v, 'Process') }
  }
}

# ========== 必需项 ==========
$BaseUrl = $env:AI_BASE_URL
$Model   = $env:AI_MODEL
$ApiKey  = $env:AI_API_KEY
if (-not $BaseUrl -or -not $Model -or -not $ApiKey) {
  throw "AI_BASE_URL / AI_MODEL / AI_API_KEY 必须配置"
}

$Tail = [int]$env:AI_TAIL
if ($Tail -le 0) { $Tail = 600 }

# Webhook：WECOM_WEBHOOK > HOOK_URL > HOOK_KEY
$Webhook = $env:WECOM_WEBHOOK
if (-not $Webhook) {
  if ($env:HOOK_URL) { $Webhook = $env:HOOK_URL }
  elseif ($env:HOOK_KEY) { $Webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=$($env:HOOK_KEY)" }
}
if (-not $Webhook) { throw "未配置企微 Webhook（WECOM_WEBHOOK / HOOK_URL / HOOK_KEY）" }

# ========== 日志路径（参数优先；否则 LOG_DIR + 当日）==========
if (-not $LogPath) {
  if (-not $env:LOG_DIR) { throw "未配置 LOG_DIR" }
  $today   = (Get-Date).ToString('yyyyMMdd')
  $LogPath = Join-Path $env:LOG_DIR ("better-genshin-impact{0}.log" -f $today)
}
if (-not (Test-Path -LiteralPath $LogPath)) { throw "找不到日志文件：$LogPath" }

# ========== 读取日志尾部 N 行（按 GBK 解码）==========
$bytes = [System.IO.File]::ReadAllBytes($LogPath)
$gbk   = [System.Text.Encoding]::GetEncoding(936) # GBK
$text  = $gbk.GetString($bytes)
$lines = $text -split "(`r`n|`n|`r)"
$tailText = ($lines | Select-Object -Last $Tail) -join "`n"

# ========== 提示词 & 调用 /chat/completions ==========
$sys = @'
你是 BetterGI（日常自动化游戏日活）日志分析助手。BetterGI 用于自动执行一条龙（日活）：识别队伍→传送→到点→交互/战斗→领奖/每日委托。你的任务是基于运行日志判断每次自动执行是否成功，并给出判断依据。

【分段规则（以时间戳为准，连续时间段切分）】
- 相邻两行时间戳间隔 ≥ 120 秒即切分；仅输出最近 8 段。
【每段一行，用全角竖线分隔】
[开始HH:MM:SS–结束HH:MM:SS] 运行：<正常/异常> ｜ 委托：<已领取/未领取/不涉及> ｜ 因：<≈16字> ｜ 证：<2–3个原文短语>
'@

$user = "以下是BetterGI日志末尾${Tail}行：`n`n$tailText"

$body = @{
  model = $Model
  messages = @(
    @{ role='system'; content=$sys },
    @{ role='user';   content=$user }
  )
  temperature = 0
  seed = 7
} | ConvertTo-Json -Depth 12

try {
  $resp = Invoke-RestMethod -Method Post -Uri ("{0}/chat/completions" -f $BaseUrl) `
            -Headers @{ Authorization = "Bearer $ApiKey" } `
            -ContentType 'application/json; charset=utf-8' `
            -Body $body
  $summary = ($resp.choices[0].message.content | Out-String).Trim()
  if (-not $summary) { $summary = 'AI分析失败：返回为空' }
}
catch {
  $summary = "AI分析失败：" + $_.Exception.Message
}

# 企微消息长度控制
$maxLen = 1800
if ($summary.Length -gt $maxLen) { $summary = $summary.Substring(0, $maxLen) + '…' }

# ========== 发送企业微信 ==========
$wx = @{ msgtype='text'; text=@{ content = $summary } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri $Webhook -Method Post -Body $wx -ContentType 'application/json; charset=utf-8'

Write-Host "[OK] 已发送AI简报到企业微信"

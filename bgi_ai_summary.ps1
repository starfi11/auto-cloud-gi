param(
  [string]$LogPath
)

$ErrorActionPreference = 'Stop'

# ================= 读取 config.ini 到进程环境 =================
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

# ================= 必需项 =================
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

# ================= 日志路径（参数优先；否则 LOG_DIR + 当日） =================
if (-not $LogPath) {
  if (-not $env:LOG_DIR) { throw "未配置 LOG_DIR" }
  $today   = (Get-Date).ToString('yyyyMMdd')
  $LogPath = Join-Path $env:LOG_DIR ("better-genshin-impact{0}.log" -f $today)
}
if (-not (Test-Path -LiteralPath $LogPath)) { throw "找不到日志文件：$LogPath" }

# ================= 读取日志尾部 N 行（UTF-8） =================
# 若日志在写入中，Get-Content 也能正常拉取尾部行
$tailLines = Get-Content -LiteralPath $LogPath -Encoding UTF8 -Tail $Tail
$tailText  = ($tailLines -join "`n")

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

# ================== 用 HttpClient 调千问（UTF-8 字节） ==================
$bodyObj  = @{
  model = $Model
  messages = @(
    @{ role='system'; content=$sys },
    @{ role='user';   content=$user }
  )
  temperature = 0
  seed = 7
}
$bodyJson  = $bodyObj | ConvertTo-Json -Depth 12
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)

$handler = [System.Net.Http.HttpClientHandler]::new()
$client  = [System.Net.Http.HttpClient]::new($handler)
$client.DefaultRequestHeaders.Add("Authorization","Bearer $ApiKey")
$client.DefaultRequestHeaders.Add("Accept","application/json")
$client.DefaultRequestHeaders.Add("Accept-Charset","utf-8")

$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, ("{0}/chat/completions" -f $BaseUrl))
$content = [System.Net.Http.ByteArrayContent]::new([byte[]]$bodyBytes)
$content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/json")
$content.Headers.ContentType.CharSet = "utf-8"
$req.Content = $content

$respMsg   = $client.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
$respBytes = $respMsg.Content.ReadAsByteArrayAsync().Result
$respText  = [System.Text.Encoding]::UTF8.GetString($respBytes)
$resp      = $respText | ConvertFrom-Json
$summary   = ($resp.choices[0].message.content | Out-String).Trim()
if (-not $summary) { $summary = 'AI分析失败：返回为空' }

# 限长
$maxLen = 1800
if ($summary.Length -gt $maxLen) { $summary = $summary.Substring(0, $maxLen) + '…' }

# ================== 发企业微信（HttpClient + UTF-8 字节） ==================
$wxObj   = @{ msgtype='text'; text=@{ content = $summary } }
$wxJson  = $wxObj | ConvertTo-Json -Depth 5
$wxBytes = [System.Text.Encoding]::UTF8.GetBytes($wxJson)

$wreq = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $Webhook)
$wreq.Content = [System.Net.Http.ByteArrayContent]::new([byte[]]$wxBytes)
$wreq.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/json")
$wreq.Content.Headers.ContentType.CharSet = "utf-8"
$client.SendAsync($wreq).Result | Out-Null

Write-Host "[OK] 已发送AI简报到企业微信"

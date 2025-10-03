param(
  [string]$LogPath
)

$ErrorActionPreference = 'Stop'

# ================= 读取 config.ini 到进程环境 =================
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir    = Resolve-Path (Join-Path $ScriptDir "..")
$configPath = Join-Path $RootDir 'config.ini'

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
你接下来需要阅读一份 BetterGI 运行日志，并根据日志内容做出最终判断。  

【任务目标】  
- 判断本次日活执行是否成功。  
- 判定的最高分水岭是“领取每日委托奖励”：  
  - 如果出现“领取每日委托奖励成功/完成” → 本次运行视为正常；即使过程中有小异常，也可以在结果后附简短说明。  
  - 如果始终没有出现领取每日委托奖励成功 → 本次运行视为异常。  
  - 如果出现了“领取每日委托奖励失败/未完成”，视为运行异常
  - 如果同时出现了“领取每日委托奖励成功/完成”和“失败/未完成”，视为运行正常，需要在结果后附简短说明（说明过程中有问题）

【输出格式（严格遵守，仅一行，不要标题/总结/代码块）】  
[开始HH:MM:SS–结束HH:MM:SS] 运行：<正常/异常> ｜ 委托：<已领取/未领取/不涉及> ｜ 因：<≈16字原因> ｜ 证：<2–3个关键原文短语>  
- 注意，开始时间取日志第一行log的时间，结束取日志最后一行log的时间
【运行=正常 的条件】  
- 日志中出现完整的链式成功信号，最终成功领取每日委托奖励。  
- 即便过程中有 WARN/重试，但最终完成了委托奖励领取，则视为正常。  

【运行=异常 的常见原因（择一填写到“因”字段，证中给出原文短语）】  
- 队伍识别失败/置信度过低  
- 地图/传送失败  
- 对话/交互失败  
- 资源/配置不匹配（如树脂不足）  
- 焦点/遮挡/UI 比例问题  
（采集晶蝶相关的回放失败可忽略，不影响最终判定）  

【每日委托判定规则】  
- 若日志出现“每日委托/前往冒险家协会领取奖励/委托按钮/历练点/凯瑟琳”等：  
  - 出现领取成功/完成 → 委托=已领取  
  - 只出现打不开/未找到按钮/对话失败 → 委托=未领取  
- 日志未涉及 → 委托=不涉及  

【示例（仅示意，勿照抄）】  
[07:03:54–07:20:16] 运行：异常 ｜ 委托：未领取 ｜ 因：领取每日委托奖励失败/未完成 ｜ 证：‘识别橙色区域置信度较低’、‘领取每日委托奖励失败/未完成’、‘未进入对话’ | ‘额外说明：...’
[09:03:46–09:24:23] 运行：正常 ｜ 委托：已领取 ｜ 因：领取每日委托奖励成功 ｜ 证：‘领取每日委托奖励成功’、‘识别到每日委托’  

【强约束】  
- 只输出一行结果。  
- 不要输出多段、不带格式的解释或标题。  
- “因”必须精炼至约16字，“证”只摘抄2–3个日志原文短语。  
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

# ====== 将 AI 的结果原样发送到 FC ======
if ($EnableFcRetry) {
  $url = $env:FC_URL
  $ak  = $env:ALIBABA_CLOUD_ACCESS_KEY_ID
  $sk  = $env:ALIBABA_CLOUD_ACCESS_KEY_SECRET
  $sts = $env:ALIBABA_CLOUD_SECURITY_TOKEN

  $date = (Get-Date).ToUniversalTime().ToString("s") + "Z"   # ISO8601 UTC
  $bodyBytes = [Text.Encoding]::UTF8.GetBytes($summary)

  $extra = @{ 'x-acs-date' = $date }
  if ($sts) { $extra['x-acs-security-token'] = $sts }

  $auth = Get-AcsAuthorization -Method 'POST' -Url $url -BodyBytes $bodyBytes -ExtraHeaders $extra -Ak $ak -Sk $sk

  $hc  = [System.Net.Http.HttpClient]::new()
  $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $url)
  $content = [System.Net.Http.ByteArrayContent]::new([byte[]]$bodyBytes)
  $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("text/plain")
  $content.Headers.ContentType.CharSet = "utf-8"
  $req.Content = $content
  $req.Headers.Add('x-acs-date', $date)
  if ($sts) { $req.Headers.Add('x-acs-security-token', $sts) }
  $req.Headers.Add('authorization', $auth)

  $resp = $hc.SendAsync($req).Result
  if ($resp.IsSuccessStatusCode) { Write-Information "[OK] 已上送到 FC" } else { Write-Warning "[WARN] 上送 FC 失败 $($resp.StatusCode)" }
}


# ================= 修正版：FC HTTP 触发器 V3 签名与调用 ==================
function Set-ImdsSts {
  try {
    $role = (Invoke-RestMethod -Uri "http://100.100.100.200/latest/meta-data/RAM/security-credentials/").Trim()
    if (-not $role) { return $false }
    $c = Invoke-RestMethod -Uri "http://100.100.100.200/latest/meta-data/RAM/security-credentials/$role"
    $env:ALIBABA_CLOUD_ACCESS_KEY_ID     = $c.AccessKeyId
    $env:ALIBABA_CLOUD_ACCESS_KEY_SECRET = $c.AccessKeySecret
    $env:ALIBABA_CLOUD_SECURITY_TOKEN    = $c.SecurityToken
    $env:ALIBABA_CLOUD_STS_EXPIRES       = $c.Expiration
    return $true
  } catch { return $false }
}

# 若临近过期则刷新 STS
$need = $true
if ($env:ALIBABA_CLOUD_STS_EXPIRES) {
  try {
    $exp = [DateTimeOffset]::Parse($env:ALIBABA_CLOUD_STS_EXPIRES)
    if ($exp - (Get-Date) -gt [TimeSpan]::FromMinutes(5)) { $need = $false }
  } catch { $need = $true }
}
if ($need) { if (-not (Set-ImdsSts)) { throw "无法从 IMDS 获取 STS 凭证" } }

# RFC3986 严格编码
function Encode-RFC3986([string]$s) {
  $bytes = [Text.Encoding]::UTF8.GetBytes($s)
  $sb = New-Object System.Text.StringBuilder
  foreach ($b in $bytes) {
    $ch = [char]$b
    if ( ($b -ge 0x30 -and $b -le 0x39) -or ($b -ge 0x41 -and $b -le 0x5A) -or
         ($b -ge 0x61 -and $b -le 0x7A) -or $ch -in @('-', '.', '_', '~') ) {
      [void]$sb.Append($ch)
    } else {
      [void]$sb.Append(('%{0:X2}' -f $b))
    }
  }
  $sb.ToString()
}

function Get-Acs3Authorization(
  [string]$Method,[string]$Url,[byte[]]$Body,[hashtable]$Headers,[string]$Ak,[string]$Sk
) {
  $u = [Uri]$Url
  $methodUp = $Method.ToUpperInvariant()

  # 1) CanonicalURI：逐段编码；确保 $ → %24
  $rawSegs = $u.AbsolutePath.Split('/') | ForEach-Object { if ($_ -ne '') { $_ } }
  if ($rawSegs.Count -eq 0) { $canonUri = '/' }
  else {
    $encSegs = $rawSegs | ForEach-Object { Encode-RFC3986 $_ }
    $canonUri = '/' + ($encSegs -join '/')
  }
  $canonUri = $canonUri -replace '\$', '%24'

  # 2) CanonicalQueryString
  $qs = if ($u.Query.StartsWith('?')) { $u.Query.Substring(1) } else { $u.Query }
  $qDict = @{}
  if ($qs) {
    foreach ($pair in $qs -split '&') {
      if ($pair -eq '') { continue }
      $kv = $pair.Split('=',2)
      $k  = [Uri]::UnescapeDataString($kv[0])
      $v  = if ($kv.Count -gt 1) { [Uri]::UnescapeDataString($kv[1]) } else { '' }
      if (-not $qDict.ContainsKey($k)) { $qDict[$k] = @() }
      $qDict[$k] += $v
    }
  }
  $qLines = @()
  foreach ($k in ($qDict.Keys | Sort-Object)) {
    foreach ($v in ($qDict[$k] | Sort-Object)) {
      $qLines += ("{0}={1}" -f (Encode-RFC3986 $k), (Encode-RFC3986 $v))
    }
  }
  $canonQuery = ($qLines -join '&')

  # 3) 计算 Body Hash，填入头，参与签名
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try { $payloadHash = ($sha.ComputeHash($Body) | ForEach-Object { $_.ToString("x2") }) -join '' }
  finally { $sha.Dispose() }
  $Headers['x-acs-content-sha256'] = $payloadHash

  # 4) CanonicalHeaders + SignedHeaders
  $h = @{}
  foreach ($k in $Headers.Keys) { $h[$k.ToLowerInvariant()] = ($Headers[$k]).ToString().Trim() }

  # host 含端口（非默认端口）
  $hostHeader = $u.Host
  if (-not $u.IsDefaultPort -and $u.Port -gt 0) { $hostHeader = "${hostHeader}:$($u.Port)" }
  $h['host'] = $hostHeader

  $signedHeaderNames = @('host','x-acs-date','x-acs-content-sha256')
  if ($h.ContainsKey('x-acs-security-token') -and $h['x-acs-security-token']) { $signedHeaderNames += 'x-acs-security-token' }
  $signedHeaderNames = $signedHeaderNames | Sort-Object

  $canonHeaders = ($signedHeaderNames | ForEach-Object { "{0}:{1}`n" -f $_, $h[$_] }) -join ''
  $signedHeaders = ($signedHeaderNames -join ';')

  # 5) CanonicalRequest
  $canonicalRequest = ($methodUp + "`n" + $canonUri + "`n" + $canonQuery + "`n" + $canonHeaders + "`n" + $signedHeaders + "`n" + $payloadHash)

  # 6) StringToSign 与 Signature（hex 小写）
  $sha2 = [System.Security.Cryptography.SHA256]::Create()
  try { $hashedCanon = ($sha2.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonicalRequest)) | ForEach-Object { $_.ToString("x2") }) -join '' }
  finally { $sha2.Dispose() }
  $stringToSign = "ACS3-HMAC-SHA256`n$hashedCanon"

  $hmac = [System.Security.Cryptography.HMACSHA256]::new([byte[]][Text.Encoding]::UTF8.GetBytes($Sk))
  try { $sigHex = ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($stringToSign)) | ForEach-Object { $_.ToString("x2") }) -join '' }
  finally { $hmac.Dispose() }

  "ACS3-HMAC-SHA256 Credential=$Ak,SignedHeaders=$signedHeaders,Signature=$sigHex"
}

# ================= 实际调用 ==================
Write-Host "[DBG] 准备调用 FC..."
$url = $env:FC_URL
$ak  = $env:ALIBABA_CLOUD_ACCESS_KEY_ID
$sk  = $env:ALIBABA_CLOUD_ACCESS_KEY_SECRET
$sts = $env:ALIBABA_CLOUD_SECURITY_TOKEN

$payloadObj = @{ text = $summary }
$bodyJson   = $payloadObj | ConvertTo-Json -Depth 5
$bodyBytes  = [Text.Encoding]::UTF8.GetBytes($bodyJson)

# 头部（与签名保持一致）
$headers = @{
  'x-acs-date' = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
  'Content-Type' = 'application/json; charset=utf-8'
}
if ($sts) { $headers['x-acs-security-token'] = $sts }

$auth = Get-Acs3Authorization -Method 'POST' -Url $url -Body $bodyBytes -Headers $headers -Ak $ak -Sk $sk

$hc  = [System.Net.Http.HttpClient]::new()
$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $url)

$content = [System.Net.Http.ByteArrayContent]::new([byte[]]$bodyBytes)
$content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/json")
$content.Headers.ContentType.CharSet = "utf-8"
$req.Content = $content

# 附加头（与签名一致）
$req.Headers.TryAddWithoutValidation('x-acs-date', $headers['x-acs-date']) | Out-Null
$req.Headers.TryAddWithoutValidation('x-acs-content-sha256', $headers['x-acs-content-sha256']) | Out-Null
if ($sts) { $req.Headers.TryAddWithoutValidation('x-acs-security-token', $sts) | Out-Null }
$req.Headers.TryAddWithoutValidation('Authorization', $auth) | Out-Null

$resp = $hc.SendAsync($req).Result
$respText = ''
try { $respText = $resp.Content.ReadAsStringAsync().Result } catch {}
Write-Host "[DBG] FC resp status: $($resp.StatusCode)"
if ($respText) { Write-Host "[DBG] FC resp body: $respText" }
if ($resp.IsSuccessStatusCode) { Write-Information "[OK] 已上送到 FC" } else { Write-Warning "[WARN] 上送 FC 失败 $($resp.StatusCode)" }

param(
  [string]$Profile = "genshin_cloud_bettergi",
  [string]$Scenario = "daily_default",
  [string]$IdempotencyKey = "",
  [string]$ApiBase = "http://127.0.0.1:8788",
  [string]$AssistantLogRoot = "C:/Program Files/BetterGI/log",
  [string]$AssistantLogGlob = "better-genshin-impact*.log",
  [int]$AssistantIdleSeconds = 10,
  [int]$AssistantTimeoutSeconds = 180,
  [bool]$AssistantRequireLogActivity = $false,
  [bool]$UseTextSignalWait = $false,
  [string]$QueueStrategy = "normal"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($IdempotencyKey)) {
  $IdempotencyKey = "smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

$payload = @{
  trigger = "API_TRIGGER"
  idempotency_key = $IdempotencyKey
  target_profile = $Profile
  scenario = $Scenario
  requested_policy_override = @{
    assistant_log_root = $AssistantLogRoot
    assistant_log_glob = $AssistantLogGlob
    assistant_idle_seconds = $AssistantIdleSeconds
    assistant_timeout_seconds = $AssistantTimeoutSeconds
    assistant_require_log_activity = $AssistantRequireLogActivity
    use_text_signal_wait = $UseTextSignalWait
    queue_strategy = $QueueStrategy
  }
} | ConvertTo-Json -Depth 10

$uri = "$ApiBase/api/v1/runs"
$resp = Invoke-RestMethod -Method POST -Uri $uri -ContentType "application/json" -Body $payload

if (-not $resp.ok) {
  throw "run not accepted: $($resp | ConvertTo-Json -Depth 8)"
}

$runId = $resp.receipt.run_id
Write-Host "RUN_ID=$runId"
$runId

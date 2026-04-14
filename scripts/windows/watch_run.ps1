param(
  [Parameter(Mandatory=$true)][string]$RunId,
  [string]$ApiBase = "http://127.0.0.1:8788",
  [string]$RuntimeDir = ".\\runtime",
  [int]$PollSeconds = 2
)

$ErrorActionPreference = "Stop"

$statusUri = "$ApiBase/api/v1/runs/$RunId"
$runDir = Join-Path $RuntimeDir "logs\\runs\\$RunId"
$diagPath = Join-Path $runDir "diagnostics.json"
$summaryPath = Join-Path $runDir "summary.json"

Write-Host "Watching run: $RunId"
while ($true) {
  $resp = Invoke-RestMethod -Method GET -Uri $statusUri
  $status = $resp.run.status
  $reason = $resp.run.reason
  Write-Host "status=$status reason=$reason"
  if ($status -in @("finished","failed","interrupted","risk_stopped")) { break }
  Start-Sleep -Seconds $PollSeconds
}

if (Test-Path $diagPath) {
  Write-Host "=== diagnostics.json ==="
  Get-Content $diagPath
}
if (Test-Path $summaryPath) {
  Write-Host "=== summary.json ==="
  Get-Content $summaryPath
}

# 定时截图采样（双击可运行版）

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir   = Resolve-Path (Join-Path $ScriptDir "..")
$OutRoot   = Join-Path $RootDir "logs\screens"
$IntervalSec = 10
$ErrorActionPreference = "Stop"

$ConfigFile = Join-Path $RootDir "config.ini"
$RiskQueueUrl = "http://127.0.0.1:8787/enqueue"

# 读取 Enable_RiskGuard 开关
$EnableRiskGuard = $false
if (Test-Path $ConfigFile) {
    try {
        # 找到形如 "Enable_RiskGuard=xxx" 的第一行
        $line = Get-Content $ConfigFile |
            Where-Object { $_ -match '^\s*Enable_RiskGuard\s*=' } |
            Select-Object -First 1

        if ($line) {
            $parts = $line -split '=', 2
            if ($parts.Length -ge 2) {
                $val = $parts[1].Trim()
                # 支持 true / True / 1 / yes
                if ($val -match '^(?i:true|1|yes)$') {
                    $EnableRiskGuard = $true
                }
            }
        }
    } catch {
        Write-Host "[RiskGuard] 读取 Enable_RiskGuard 失败：$($_.Exception.Message)"
    }
}

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

function Send-ToRiskQueue([string]$imgPath) {
    if (-not $EnableRiskGuard) { return }

    try {
        $body = @{ path = $imgPath } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $RiskQueueUrl -Method Post -Body $body -ContentType "application/json" | Out-Null
    } catch {
        # 风控服务挂了，不影响截图本身
        Write-Host "[RiskGuard] enqueue failed: $($_.Exception.Message)"
    }
}

function Get-DayDir {
    $day = (Get-Date).ToString("yyyyMMdd")
    $dir = Join-Path $OutRoot $day
    if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    return $dir
}

function Get-VirtualBounds {
    $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
    return @{
        X = $vs.X; Y = $vs.Y; W = $vs.Width; H = $vs.Height
    }
}

function Capture-Once {
    $bounds = Get-VirtualBounds
    if ($bounds.W -le 0 -or $bounds.H -le 0) { return }

    $bmp = New-Object System.Drawing.Bitmap($bounds.W, $bounds.H, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $gfx.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
        $dir = Get-DayDir
        $name = (Get-Date).ToString("HHmmss.fff") + ".png"
        $path = Join-Path $dir $name
        $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        # 根据风控开关决定是否投递到本地消息队列
        Send-ToRiskQueue -imgPath $path
    }
    finally {
        $gfx.Dispose()
        $bmp.Dispose()
    }
}

while ($true) {
    try { Capture-Once } catch { }
    Start-Sleep -Seconds $IntervalSec
}

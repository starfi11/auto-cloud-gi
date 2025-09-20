# 定时截图采样（双击可运行版）

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir   = Resolve-Path (Join-Path $ScriptDir "..")
$OutRoot   = Join-Path $RootDir "logs\screens"
$IntervalSec = 10
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

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
